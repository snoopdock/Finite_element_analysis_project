"""Bounded execution of precomputed verification orchestration plans."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph
from audit_engine.semantic_audit.graph.analysis.identity import deterministic_id
from audit_engine.semantic_audit.graph.analysis.results import GraphAnalysisResult
from audit_engine.semantic_audit.verification.models import VerificationDecision, VerificationObligation
from audit_engine.semantic_audit.verification.receipts import VerificationReceipt
from audit_engine.semantic_audit.verification.service import VerificationService

from .models import ORCHESTRATION_EXECUTION_SCHEMA_VERSION, OrchestrationPlan, RoutePlanningStatus
from .policy import OrchestrationPolicy, evidence_requirement_satisfied


class ActionExecutionStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"


class ObjectiveExecutionStatus(str, Enum):
    SATISFIED = "satisfied"
    EXHAUSTED = "exhausted"
    UNSCHEDULED = "unscheduled"
    FAILED = "failed"


@dataclass(frozen=True)
class VerificationActionExecution:
    action_id: str
    verifier_id: str
    status: ActionExecutionStatus
    cost_units: int
    receipt_id: str | None = None
    decision: str | None = None
    evidence_state: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "verifier_id": self.verifier_id,
            "status": self.status.value,
            "cost_units": self.cost_units,
            "receipt_id": self.receipt_id,
            "decision": self.decision,
            "evidence_state": self.evidence_state,
            "error": self.error,
        }


@dataclass(frozen=True)
class ObjectiveExecutionResult:
    objective_id: str
    obligation_id: str
    status: ObjectiveExecutionStatus
    actions: tuple[VerificationActionExecution, ...] = field(default_factory=tuple)
    terminal_receipt_id: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective_id": self.objective_id,
            "obligation_id": self.obligation_id,
            "status": self.status.value,
            "terminal_receipt_id": self.terminal_receipt_id,
            "reason": self.reason,
            "actions": [item.to_dict() for item in self.actions],
        }


@dataclass(frozen=True)
class OrchestrationExecutionResult:
    execution_id: str
    plan_id: str
    policy_version: str
    objective_results: tuple[ObjectiveExecutionResult, ...]
    receipts: tuple[VerificationReceipt, ...]
    consumed_cost_units: int
    consumed_verifier_runs: int
    budget_cost_units: int
    budget_verifier_runs: int
    schema_version: str = ORCHESTRATION_EXECUTION_SCHEMA_VERSION

    @property
    def remaining_cost_units(self) -> int:
        return self.budget_cost_units - self.consumed_cost_units

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "execution_id": self.execution_id,
            "plan_id": self.plan_id,
            "policy_version": self.policy_version,
            "consumed_cost_units": self.consumed_cost_units,
            "consumed_verifier_runs": self.consumed_verifier_runs,
            "budget_cost_units": self.budget_cost_units,
            "budget_verifier_runs": self.budget_verifier_runs,
            "remaining_cost_units": self.remaining_cost_units,
            "objective_results": [item.to_dict() for item in self.objective_results],
            "receipts": [item.to_dict() for item in self.receipts],
        }


def execute_orchestration_plan(
    *,
    plan: OrchestrationPlan,
    obligations: Mapping[str, VerificationObligation],
    analysis_results: Mapping[str, GraphAnalysisResult],
    verification_service: VerificationService,
    semantic_graphs: Mapping[str, SemanticGraph] | None = None,
    policy: OrchestrationPolicy | None = None,
) -> OrchestrationExecutionResult:
    policy = policy or OrchestrationPolicy()
    if policy.version != plan.policy_version:
        raise ValueError("Execution policy version does not match the plan.")
    semantic_graphs = semantic_graphs or {}
    consumed_cost = 0
    consumed_runs = 0
    results: list[ObjectiveExecutionResult] = []
    receipts: list[VerificationReceipt] = []

    for route in plan.routes:
        objective = route.objective
        if route.status is not RoutePlanningStatus.SCHEDULED:
            results.append(
                ObjectiveExecutionResult(
                    objective_id=objective.objective_id,
                    obligation_id=objective.obligation_id,
                    status=ObjectiveExecutionStatus.UNSCHEDULED,
                    reason=route.reason or route.status.value,
                )
            )
            continue
        obligation = obligations.get(objective.obligation_id)
        if obligation is None:
            raise ValueError(f"Missing obligation required by plan: {objective.obligation_id}")
        analysis = analysis_results.get(obligation.source_analysis_id)
        if analysis is None:
            raise ValueError(f"Missing source analysis: {obligation.source_analysis_id}")
        graph = semantic_graphs.get(obligation.source_analysis_id)
        action_results: list[VerificationActionExecution] = []
        terminal_receipt: VerificationReceipt | None = None
        objective_failed = False

        for action in route.actions:
            if consumed_cost + action.cost_units > plan.budget.total_cost_units:
                raise RuntimeError("Execution would exceed the planned cost budget.")
            if consumed_runs + 1 > plan.budget.max_verifier_runs:
                raise RuntimeError("Execution would exceed the planned verifier-run budget.")
            try:
                receipt = verification_service.verify(
                    obligation,
                    analysis,
                    verifier_id=action.verifier_id,
                    semantic_graph=graph,
                )
                consumed_cost += action.cost_units
                consumed_runs += 1
                receipts.append(receipt)
                action_results.append(
                    VerificationActionExecution(
                        action_id=action.action_id,
                        verifier_id=action.verifier_id,
                        status=ActionExecutionStatus.COMPLETED,
                        cost_units=action.cost_units,
                        receipt_id=receipt.receipt_id,
                        decision=receipt.decision.value,
                        evidence_state=receipt.evidence_state.value,
                    )
                )
            except Exception as exc:  # execution result preserves failure; policy decides fallback
                consumed_cost += action.cost_units
                consumed_runs += 1
                action_results.append(
                    VerificationActionExecution(
                        action_id=action.action_id,
                        verifier_id=action.verifier_id,
                        status=ActionExecutionStatus.FAILED,
                        cost_units=action.cost_units,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )
                if policy.fallback_on_error:
                    continue
                objective_failed = True
                break

            if (
                receipt.decision in {VerificationDecision.CONFIRMED, VerificationDecision.REFUTED}
                and evidence_requirement_satisfied(
                    receipt.evidence_state, objective.minimum_evidence_state
                )
            ):
                terminal_receipt = receipt
                break
            if receipt.decision is VerificationDecision.ERROR and not policy.fallback_on_error:
                objective_failed = True
                break
            if receipt.decision is VerificationDecision.INCONCLUSIVE and not policy.fallback_on_inconclusive:
                break

        if terminal_receipt is not None:
            status = ObjectiveExecutionStatus.SATISFIED
            reason = "terminal_verification_receipt_satisfies_objective"
        elif objective_failed:
            status = ObjectiveExecutionStatus.FAILED
            reason = "verification_action_failed"
        else:
            status = ObjectiveExecutionStatus.EXHAUSTED
            reason = "planned_verifier_route_exhausted_without_satisfying_objective"
        results.append(
            ObjectiveExecutionResult(
                objective_id=objective.objective_id,
                obligation_id=objective.obligation_id,
                status=status,
                actions=tuple(action_results),
                terminal_receipt_id=terminal_receipt.receipt_id if terminal_receipt else None,
                reason=reason,
            )
        )

    identity = {
        "plan_id": plan.plan_id,
        "policy_version": plan.policy_version,
        "objective_results": [item.to_dict() for item in results],
        "receipt_ids": [item.receipt_id for item in receipts],
        "consumed_cost_units": consumed_cost,
        "consumed_verifier_runs": consumed_runs,
    }
    return OrchestrationExecutionResult(
        execution_id=deterministic_id("audit-orchestration-execution", identity, length=28),
        plan_id=plan.plan_id,
        policy_version=plan.policy_version,
        objective_results=tuple(results),
        receipts=tuple(receipts),
        consumed_cost_units=consumed_cost,
        consumed_verifier_runs=consumed_runs,
        budget_cost_units=plan.budget.total_cost_units,
        budget_verifier_runs=plan.budget.max_verifier_runs,
    )
