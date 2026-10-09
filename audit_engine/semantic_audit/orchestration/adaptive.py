"""Bounded adaptive orchestration session over immutable plan/execution rounds."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph
from audit_engine.semantic_audit.graph.analysis.identity import deterministic_id
from audit_engine.semantic_audit.graph.analysis.results import GraphAnalysisResult
from audit_engine.semantic_audit.verification.models import VerificationObligation
from audit_engine.semantic_audit.verification.registry import VerifierRegistry
from audit_engine.semantic_audit.verification.service import VerificationService

from .execution import ObjectiveExecutionStatus, OrchestrationExecutionResult, execute_orchestration_plan
from .models import AuditBudget, OrchestrationPlan
from .policy import OrchestrationPolicy
from .profiles import VerifierProfileCatalog
from .replanning import (
    AdaptiveReplan,
    AdaptiveReplanningPolicy,
    RemainingAuditBudget,
    build_adaptive_replan,
)


ADAPTIVE_SESSION_SCHEMA_VERSION = "semantic_adaptive_verification_session/v1"


class AdaptiveSessionStatus(str, Enum):
    SATISFIED = "satisfied"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CAPABILITY_EXHAUSTED = "capability_exhausted"
    ROUND_LIMIT = "round_limit"
    POLICY_STOPPED = "policy_stopped"


@dataclass(frozen=True)
class AdaptiveRoundRecord:
    round_index: int
    plan_id: str
    execution_id: str
    consumed_cost_units: int
    consumed_verifier_runs: int
    replan_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_index": self.round_index,
            "plan_id": self.plan_id,
            "execution_id": self.execution_id,
            "consumed_cost_units": self.consumed_cost_units,
            "consumed_verifier_runs": self.consumed_verifier_runs,
            "replan_id": self.replan_id,
        }


@dataclass(frozen=True)
class AdaptiveOrchestrationSessionResult:
    session_id: str
    initial_plan_id: str
    orchestration_policy_version: str
    adaptive_policy_version: str
    original_budget: AuditBudget
    status: AdaptiveSessionStatus
    rounds: tuple[AdaptiveRoundRecord, ...]
    replans: tuple[AdaptiveReplan, ...]
    executions: tuple[OrchestrationExecutionResult, ...]
    total_consumed_cost_units: int
    total_consumed_verifier_runs: int
    unsatisfied_objective_ids: tuple[str, ...] = field(default_factory=tuple)
    terminal_reason: str | None = None
    schema_version: str = ADAPTIVE_SESSION_SCHEMA_VERSION

    @property
    def remaining_cost_units(self) -> int:
        return self.original_budget.total_cost_units - self.total_consumed_cost_units

    @property
    def remaining_verifier_runs(self) -> int:
        return self.original_budget.max_verifier_runs - self.total_consumed_verifier_runs

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "initial_plan_id": self.initial_plan_id,
            "orchestration_policy_version": self.orchestration_policy_version,
            "adaptive_policy_version": self.adaptive_policy_version,
            "status": self.status.value,
            "original_budget": self.original_budget.to_dict(),
            "total_consumed_cost_units": self.total_consumed_cost_units,
            "total_consumed_verifier_runs": self.total_consumed_verifier_runs,
            "remaining_cost_units": self.remaining_cost_units,
            "remaining_verifier_runs": self.remaining_verifier_runs,
            "unsatisfied_objective_ids": list(self.unsatisfied_objective_ids),
            "terminal_reason": self.terminal_reason,
            "rounds": [item.to_dict() for item in self.rounds],
            "replans": [item.to_dict() for item in self.replans],
            "executions": [item.to_dict() for item in self.executions],
        }


def _collect_attempted(executions: list[OrchestrationExecutionResult]) -> dict[str, frozenset[str]]:
    result: dict[str, set[str]] = {}
    for execution in executions:
        for objective_result in execution.objective_results:
            bucket = result.setdefault(objective_result.objective_id, set())
            bucket.update(action.verifier_id for action in objective_result.actions)
    return {key: frozenset(value) for key, value in result.items()}


def _latest_statuses(executions: list[OrchestrationExecutionResult]) -> dict[str, ObjectiveExecutionStatus]:
    statuses: dict[str, ObjectiveExecutionStatus] = {}
    for execution in executions:
        for result in execution.objective_results:
            statuses[result.objective_id] = result.status
    return statuses


def run_adaptive_orchestration(
    *,
    initial_plan: OrchestrationPlan,
    obligations: Mapping[str, VerificationObligation],
    analysis_results: Mapping[str, GraphAnalysisResult],
    verification_service: VerificationService,
    registry: VerifierRegistry,
    profiles: VerifierProfileCatalog,
    semantic_graphs: Mapping[str, SemanticGraph] | None = None,
    orchestration_policy: OrchestrationPolicy | None = None,
    adaptive_policy: AdaptiveReplanningPolicy | None = None,
) -> AdaptiveOrchestrationSessionResult:
    """Execute an initial plan and bounded continuation rounds.

    The session never creates findings, mutates canonical graphs, or writes audit
    memory. Every additional verifier must first appear in an immutable replan.
    """

    orchestration_policy = orchestration_policy or OrchestrationPolicy()
    adaptive_policy = adaptive_policy or AdaptiveReplanningPolicy()
    if initial_plan.policy_version != orchestration_policy.version:
        raise ValueError("Initial plan policy version does not match orchestration policy.")

    initial_objective_ids = tuple(route.objective.objective_id for route in initial_plan.routes)
    executions: list[OrchestrationExecutionResult] = []
    replans: list[AdaptiveReplan] = []
    rounds: list[AdaptiveRoundRecord] = []

    current_plan = initial_plan
    current_execution = execute_orchestration_plan(
        plan=current_plan,
        obligations=obligations,
        analysis_results=analysis_results,
        verification_service=verification_service,
        semantic_graphs=semantic_graphs,
        policy=orchestration_policy,
    )
    executions.append(current_execution)
    rounds.append(
        AdaptiveRoundRecord(
            round_index=0,
            plan_id=current_plan.plan_id,
            execution_id=current_execution.execution_id,
            consumed_cost_units=current_execution.consumed_cost_units,
            consumed_verifier_runs=current_execution.consumed_verifier_runs,
        )
    )

    for round_index in range(1, adaptive_policy.max_replanning_rounds + 1):
        latest = _latest_statuses(executions)
        if initial_objective_ids and all(
            latest.get(objective_id) is ObjectiveExecutionStatus.SATISFIED
            for objective_id in initial_objective_ids
        ):
            break
        consumed_cost = sum(item.consumed_cost_units for item in executions)
        consumed_runs = sum(item.consumed_verifier_runs for item in executions)
        remaining = RemainingAuditBudget.from_consumption(
            initial_plan.budget,
            consumed_cost_units=consumed_cost,
            consumed_verifier_runs=consumed_runs,
        )
        replan = build_adaptive_replan(
            source_plan=current_plan,
            source_execution=current_execution,
            obligations=obligations,
            registry=registry,
            profiles=profiles,
            remaining_budget=remaining,
            cumulative_attempted_verifiers=_collect_attempted(executions),
            round_index=round_index,
            orchestration_policy=orchestration_policy,
            adaptive_policy=adaptive_policy,
        )
        replans.append(replan)
        if replan.continuation_plan is None:
            break
        current_plan = replan.continuation_plan
        current_execution = execute_orchestration_plan(
            plan=current_plan,
            obligations=obligations,
            analysis_results=analysis_results,
            verification_service=verification_service,
            semantic_graphs=semantic_graphs,
            policy=orchestration_policy,
        )
        executions.append(current_execution)
        rounds.append(
            AdaptiveRoundRecord(
                round_index=round_index,
                plan_id=current_plan.plan_id,
                execution_id=current_execution.execution_id,
                consumed_cost_units=current_execution.consumed_cost_units,
                consumed_verifier_runs=current_execution.consumed_verifier_runs,
                replan_id=replan.replan_id,
            )
        )

    latest = _latest_statuses(executions)
    unsatisfied = tuple(
        objective_id
        for objective_id in initial_objective_ids
        if latest.get(objective_id) is not ObjectiveExecutionStatus.SATISFIED
    )
    total_cost = sum(item.consumed_cost_units for item in executions)
    total_runs = sum(item.consumed_verifier_runs for item in executions)
    remaining = RemainingAuditBudget.from_consumption(
        initial_plan.budget,
        consumed_cost_units=total_cost,
        consumed_verifier_runs=total_runs,
    )

    if not unsatisfied:
        status = AdaptiveSessionStatus.SATISFIED
        terminal_reason = "all_initial_objectives_satisfied"
    elif not remaining.can_execute:
        status = AdaptiveSessionStatus.BUDGET_EXHAUSTED
        terminal_reason = "original_hard_budget_exhausted"
    elif len(replans) >= adaptive_policy.max_replanning_rounds and replans and replans[-1].continuation_plan is not None:
        status = AdaptiveSessionStatus.ROUND_LIMIT
        terminal_reason = "adaptive_replanning_round_limit_reached"
    elif replans and all(
        decision.disposition.value.startswith("no_replan_policy")
        for decision in replans[-1].decisions
        if decision.objective_id in unsatisfied
    ):
        status = AdaptiveSessionStatus.POLICY_STOPPED
        terminal_reason = "adaptive_policy_stopped_remaining_objectives"
    else:
        status = AdaptiveSessionStatus.CAPABILITY_EXHAUSTED
        terminal_reason = "no_further_eligible_unattempted_verifier"

    identity = {
        "initial_plan_id": initial_plan.plan_id,
        "orchestration_policy_version": orchestration_policy.version,
        "adaptive_policy_version": adaptive_policy.version,
        "rounds": [item.to_dict() for item in rounds],
        "replan_ids": [item.replan_id for item in replans],
        "execution_ids": [item.execution_id for item in executions],
        "status": status.value,
        "unsatisfied_objective_ids": list(unsatisfied),
        "total_consumed_cost_units": total_cost,
        "total_consumed_verifier_runs": total_runs,
    }
    return AdaptiveOrchestrationSessionResult(
        session_id=deterministic_id("adaptive-verification-session", identity, length=28),
        initial_plan_id=initial_plan.plan_id,
        orchestration_policy_version=orchestration_policy.version,
        adaptive_policy_version=adaptive_policy.version,
        original_budget=initial_plan.budget,
        status=status,
        rounds=tuple(rounds),
        replans=tuple(replans),
        executions=tuple(executions),
        total_consumed_cost_units=total_cost,
        total_consumed_verifier_runs=total_runs,
        unsatisfied_objective_ids=unsatisfied,
        terminal_reason=terminal_reason,
    )
