"""Adaptive, outcome-driven replanning for G3.3 verification orchestration.

Replanning reacts only to explicit execution outcomes. It may select another
*already registered and profiled* verifier within the remaining hard budget.
It does not create findings, mutate audit memory, or treat verifier output as
instructions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from audit_engine.semantic_audit.graph.analysis.identity import deterministic_id
from audit_engine.semantic_audit.verification.models import VerificationObligation
from audit_engine.semantic_audit.verification.registry import VerifierRegistry

from .execution import ObjectiveExecutionStatus, OrchestrationExecutionResult
from .models import (
    AuditBudget,
    OrchestrationPlan,
    PlannedVerifierAction,
    RoutePlanningStatus,
    VerificationRoute,
    priority_sort_key,
)
from .planner import eligible_profiles
from .policy import OrchestrationPolicy
from .profiles import VerifierProfileCatalog


ADAPTIVE_REPLAN_SCHEMA_VERSION = "semantic_adaptive_verification_replan/v1"
ADAPTIVE_REPLANNING_POLICY_VERSION = "adaptive_verification_replanning_policy/v1"


class ReplanningDisposition(str, Enum):
    REPLAN_SCHEDULED = "replan_scheduled"
    NO_REPLAN_SATISFIED = "no_replan_satisfied"
    NO_REPLAN_UNSCHEDULED = "no_replan_unscheduled"
    NO_REPLAN_POLICY = "no_replan_policy"
    NO_REPLAN_CAPABILITY = "no_replan_capability"
    NO_REPLAN_BUDGET = "no_replan_budget"
    NO_REPLAN_ROUND_LIMIT = "no_replan_round_limit"


@dataclass(frozen=True)
class RemainingAuditBudget:
    """Remaining portion of the original hard budget; zero is valid."""

    cost_units: int
    verifier_runs: int
    allowed_execution_modes: tuple

    def __post_init__(self) -> None:
        if self.cost_units < 0 or self.verifier_runs < 0:
            raise ValueError("Remaining budget cannot be negative.")
        if not self.allowed_execution_modes:
            raise ValueError("At least one execution mode must remain allowed.")

    @classmethod
    def from_consumption(
        cls,
        original: AuditBudget,
        *,
        consumed_cost_units: int,
        consumed_verifier_runs: int,
    ) -> "RemainingAuditBudget":
        if consumed_cost_units < 0 or consumed_verifier_runs < 0:
            raise ValueError("Consumed budget cannot be negative.")
        if consumed_cost_units > original.total_cost_units:
            raise ValueError("Consumed cost exceeds the original hard budget.")
        if consumed_verifier_runs > original.max_verifier_runs:
            raise ValueError("Consumed verifier runs exceed the original hard budget.")
        return cls(
            cost_units=original.total_cost_units - consumed_cost_units,
            verifier_runs=original.max_verifier_runs - consumed_verifier_runs,
            allowed_execution_modes=original.allowed_execution_modes,
        )

    @property
    def can_execute(self) -> bool:
        return self.cost_units > 0 and self.verifier_runs > 0

    def as_audit_budget(self) -> AuditBudget:
        if not self.can_execute:
            raise ValueError("A zero remaining budget cannot be converted to AuditBudget.")
        return AuditBudget(
            total_cost_units=self.cost_units,
            max_verifier_runs=self.verifier_runs,
            allowed_execution_modes=self.allowed_execution_modes,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "cost_units": self.cost_units,
            "verifier_runs": self.verifier_runs,
            "allowed_execution_modes": [mode.value for mode in self.allowed_execution_modes],
        }


@dataclass(frozen=True)
class AdaptiveReplanningPolicy:
    """Policy controlling whether another bounded verification round is legal."""

    version: str = ADAPTIVE_REPLANNING_POLICY_VERSION
    max_replanning_rounds: int = 2
    max_new_actions_per_objective: int = 1
    replan_on_exhausted: bool = True
    replan_on_failed: bool = False
    exclude_attempted_verifiers: bool = True

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("Adaptive replanning policy version must be non-empty.")
        if self.max_replanning_rounds < 0:
            raise ValueError("max_replanning_rounds cannot be negative.")
        if self.max_new_actions_per_objective < 1:
            raise ValueError("max_new_actions_per_objective must be at least 1.")


@dataclass(frozen=True)
class AdaptiveObjectiveDecision:
    objective_id: str
    obligation_id: str
    prior_status: ObjectiveExecutionStatus
    disposition: ReplanningDisposition
    attempted_verifier_ids: tuple[str, ...] = field(default_factory=tuple)
    selected_verifier_ids: tuple[str, ...] = field(default_factory=tuple)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective_id": self.objective_id,
            "obligation_id": self.obligation_id,
            "prior_status": self.prior_status.value,
            "disposition": self.disposition.value,
            "attempted_verifier_ids": list(self.attempted_verifier_ids),
            "selected_verifier_ids": list(self.selected_verifier_ids),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AdaptiveReplan:
    replan_id: str
    parent_plan_id: str
    source_execution_id: str
    round_index: int
    adaptive_policy_version: str
    remaining_budget_before: RemainingAuditBudget
    decisions: tuple[AdaptiveObjectiveDecision, ...]
    continuation_plan: OrchestrationPlan | None = None
    schema_version: str = ADAPTIVE_REPLAN_SCHEMA_VERSION

    @property
    def reserved_cost_units(self) -> int:
        return self.continuation_plan.reserved_cost_units if self.continuation_plan else 0

    @property
    def reserved_verifier_runs(self) -> int:
        return self.continuation_plan.reserved_verifier_runs if self.continuation_plan else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "replan_id": self.replan_id,
            "parent_plan_id": self.parent_plan_id,
            "source_execution_id": self.source_execution_id,
            "round_index": self.round_index,
            "adaptive_policy_version": self.adaptive_policy_version,
            "remaining_budget_before": self.remaining_budget_before.to_dict(),
            "reserved_cost_units": self.reserved_cost_units,
            "reserved_verifier_runs": self.reserved_verifier_runs,
            "decisions": [item.to_dict() for item in self.decisions],
            "continuation_plan": self.continuation_plan.to_dict() if self.continuation_plan else None,
        }


def _attempted_for_objective(
    objective_id: str,
    cumulative_attempted_verifiers: Mapping[str, frozenset[str] | set[str] | tuple[str, ...]],
) -> frozenset[str]:
    return frozenset(cumulative_attempted_verifiers.get(objective_id, ()))


def build_adaptive_replan(
    *,
    source_plan: OrchestrationPlan,
    source_execution: OrchestrationExecutionResult,
    obligations: Mapping[str, VerificationObligation],
    registry: VerifierRegistry,
    profiles: VerifierProfileCatalog,
    remaining_budget: RemainingAuditBudget,
    cumulative_attempted_verifiers: Mapping[str, frozenset[str] | set[str] | tuple[str, ...]],
    round_index: int,
    orchestration_policy: OrchestrationPolicy | None = None,
    adaptive_policy: AdaptiveReplanningPolicy | None = None,
) -> AdaptiveReplan:
    """Build one immutable continuation plan from observed execution outcomes."""

    orchestration_policy = orchestration_policy or OrchestrationPolicy()
    adaptive_policy = adaptive_policy or AdaptiveReplanningPolicy()
    if source_execution.plan_id != source_plan.plan_id:
        raise ValueError("Source execution is not bound to the source plan.")
    if source_plan.policy_version != orchestration_policy.version:
        raise ValueError("Source plan policy version does not match orchestration policy.")
    if round_index < 1:
        raise ValueError("round_index must be at least 1 for adaptive replanning.")

    route_by_objective = {route.objective.objective_id: route for route in source_plan.routes}
    execution_by_objective = {item.objective_id: item for item in source_execution.objective_results}
    if set(execution_by_objective) != set(route_by_objective):
        raise ValueError("Source execution objective set does not match the source plan.")

    decision_seed: dict[str, AdaptiveObjectiveDecision] = {}
    replannable = []
    for objective_id in sorted(route_by_objective):
        route = route_by_objective[objective_id]
        result = execution_by_objective[objective_id]
        attempted = tuple(sorted(_attempted_for_objective(objective_id, cumulative_attempted_verifiers)))
        if result.status is ObjectiveExecutionStatus.SATISFIED:
            decision_seed[objective_id] = AdaptiveObjectiveDecision(
                objective_id, result.obligation_id, result.status,
                ReplanningDisposition.NO_REPLAN_SATISFIED, attempted,
                reason="objective_already_satisfied",
            )
            continue
        if result.status is ObjectiveExecutionStatus.UNSCHEDULED:
            decision_seed[objective_id] = AdaptiveObjectiveDecision(
                objective_id, result.obligation_id, result.status,
                ReplanningDisposition.NO_REPLAN_UNSCHEDULED, attempted,
                reason="unscheduled_objective_is_not_replanned_implicitly",
            )
            continue
        if result.status is ObjectiveExecutionStatus.FAILED and not adaptive_policy.replan_on_failed:
            decision_seed[objective_id] = AdaptiveObjectiveDecision(
                objective_id, result.obligation_id, result.status,
                ReplanningDisposition.NO_REPLAN_POLICY, attempted,
                reason="adaptive_policy_disallows_replanning_after_failure",
            )
            continue
        if result.status is ObjectiveExecutionStatus.EXHAUSTED and not adaptive_policy.replan_on_exhausted:
            decision_seed[objective_id] = AdaptiveObjectiveDecision(
                objective_id, result.obligation_id, result.status,
                ReplanningDisposition.NO_REPLAN_POLICY, attempted,
                reason="adaptive_policy_disallows_replanning_after_exhaustion",
            )
            continue
        replannable.append(route.objective)

    if round_index > adaptive_policy.max_replanning_rounds:
        for objective in replannable:
            result = execution_by_objective[objective.objective_id]
            attempted = tuple(sorted(_attempted_for_objective(objective.objective_id, cumulative_attempted_verifiers)))
            decision_seed[objective.objective_id] = AdaptiveObjectiveDecision(
                objective.objective_id, result.obligation_id, result.status,
                ReplanningDisposition.NO_REPLAN_ROUND_LIMIT, attempted,
                reason="adaptive_replanning_round_limit_reached",
            )
        replannable = []

    if replannable and not remaining_budget.can_execute:
        for objective in replannable:
            result = execution_by_objective[objective.objective_id]
            attempted = tuple(sorted(_attempted_for_objective(objective.objective_id, cumulative_attempted_verifiers)))
            decision_seed[objective.objective_id] = AdaptiveObjectiveDecision(
                objective.objective_id, result.obligation_id, result.status,
                ReplanningDisposition.NO_REPLAN_BUDGET, attempted,
                reason="no_remaining_hard_budget",
            )
        replannable = []

    continuation_routes: list[VerificationRoute] = []
    if replannable:
        budget_view = remaining_budget.as_audit_budget()
        ordered = sorted(replannable, key=priority_sort_key)
        used_cost = 0
        used_runs = 0
        candidate_map: dict[str, list] = {}

        # Reserve one new verifier per objective before adding any additional
        # continuation actions. This preserves cross-objective coverage.
        for objective in ordered:
            obligation = obligations.get(objective.obligation_id)
            if obligation is None:
                raise ValueError(f"Unknown obligation for objective: {objective.obligation_id}")
            attempted_set = _attempted_for_objective(objective.objective_id, cumulative_attempted_verifiers)
            extra_excluded = attempted_set if adaptive_policy.exclude_attempted_verifiers else frozenset()
            candidates = eligible_profiles(
                objective=objective,
                obligation=obligation,
                registry=registry,
                profiles=profiles,
                budget=budget_view,
                policy=orchestration_policy,
                extra_excluded_verifier_ids=extra_excluded,
            )
            candidate_map[objective.objective_id] = candidates
            result = execution_by_objective[objective.objective_id]
            attempted = tuple(sorted(attempted_set))
            if not candidates:
                decision_seed[objective.objective_id] = AdaptiveObjectiveDecision(
                    objective.objective_id, result.obligation_id, result.status,
                    ReplanningDisposition.NO_REPLAN_CAPABILITY, attempted,
                    reason="no_unattempted_eligible_verifier_profile",
                )
                continue
            primary = candidates[0]
            if (
                used_cost + primary.cost_units > budget_view.total_cost_units
                or used_runs + 1 > budget_view.max_verifier_runs
            ):
                decision_seed[objective.objective_id] = AdaptiveObjectiveDecision(
                    objective.objective_id, result.obligation_id, result.status,
                    ReplanningDisposition.NO_REPLAN_BUDGET, attempted,
                    reason="remaining_budget_cannot_fund_next_verifier",
                )
                continue
            action = PlannedVerifierAction.from_profile(objective.objective_id, primary)
            used_cost += primary.cost_units
            used_runs += 1
            continuation_routes.append(
                VerificationRoute(
                    objective=objective,
                    status=RoutePlanningStatus.SCHEDULED,
                    actions=(action,),
                )
            )
            decision_seed[objective.objective_id] = AdaptiveObjectiveDecision(
                objective.objective_id, result.obligation_id, result.status,
                ReplanningDisposition.REPLAN_SCHEDULED, attempted,
                selected_verifier_ids=(primary.verifier_id,),
                reason="unattempted_eligible_verifier_selected_from_remaining_budget",
            )

        # Optionally add further bounded continuation actions from residual
        # budget, never ahead of another objective's first continuation action.
        if adaptive_policy.max_new_actions_per_objective > 1:
            updated_routes: list[VerificationRoute] = []
            for route in continuation_routes:
                actions = list(route.actions)
                selected = {a.verifier_id for a in actions}
                for profile in candidate_map[route.objective.objective_id]:
                    if profile.verifier_id in selected:
                        continue
                    if len(actions) >= adaptive_policy.max_new_actions_per_objective:
                        break
                    if used_cost + profile.cost_units > budget_view.total_cost_units:
                        continue
                    if used_runs + 1 > budget_view.max_verifier_runs:
                        break
                    actions.append(PlannedVerifierAction.from_profile(route.objective.objective_id, profile))
                    selected.add(profile.verifier_id)
                    used_cost += profile.cost_units
                    used_runs += 1
                updated_routes.append(
                    VerificationRoute(route.objective, route.status, tuple(actions), route.reason)
                )
                decision = decision_seed[route.objective.objective_id]
                decision_seed[route.objective.objective_id] = AdaptiveObjectiveDecision(
                    decision.objective_id,
                    decision.obligation_id,
                    decision.prior_status,
                    decision.disposition,
                    decision.attempted_verifier_ids,
                    tuple(a.verifier_id for a in actions),
                    decision.reason,
                )
            continuation_routes = updated_routes

    continuation_plan = None
    if continuation_routes:
        continuation_budget = remaining_budget.as_audit_budget()
        plan_identity = {
            "policy_version": orchestration_policy.version,
            "budget": continuation_budget.to_dict(),
            "routes": [route.to_dict() for route in continuation_routes],
        }
        continuation_plan = OrchestrationPlan(
            plan_id=deterministic_id("audit-orchestration-plan", plan_identity, length=28),
            policy_version=orchestration_policy.version,
            budget=continuation_budget,
            routes=tuple(continuation_routes),
        )

    decisions = tuple(decision_seed[key] for key in sorted(decision_seed))
    identity = {
        "parent_plan_id": source_plan.plan_id,
        "source_execution_id": source_execution.execution_id,
        "round_index": round_index,
        "adaptive_policy_version": adaptive_policy.version,
        "remaining_budget_before": remaining_budget.to_dict(),
        "decisions": [item.to_dict() for item in decisions],
        "continuation_plan_id": continuation_plan.plan_id if continuation_plan else None,
    }
    return AdaptiveReplan(
        replan_id=deterministic_id("adaptive-verification-replan", identity, length=28),
        parent_plan_id=source_plan.plan_id,
        source_execution_id=source_execution.execution_id,
        round_index=round_index,
        adaptive_policy_version=adaptive_policy.version,
        remaining_budget_before=remaining_budget,
        decisions=decisions,
        continuation_plan=continuation_plan,
    )
