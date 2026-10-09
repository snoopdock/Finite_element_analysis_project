"""G3.3.2 bridge between incremental re-verification and audit orchestration.

This module is intentionally outside both ``evolution`` and ``orchestration``.
It may depend on both layers, but neither layer depends on it.  The bridge
reconstructs explicit prior verification intent against an after-snapshot,
turns eligible receipt re-verification tasks into orchestration objectives,
and reconciles orchestration receipts back to historical receipt identities.

It does *not* create findings, mutate finding lifecycle, promote candidate
knowledge, mutate the canonical graph, or write long-term memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph
from audit_engine.semantic_audit.evolution.execution import ReverificationReplayCatalog
from audit_engine.semantic_audit.evolution.incremental import IncrementalReverificationResult
from audit_engine.semantic_audit.evolution.reconciliation import ArtifactReconciliation, reconcile_receipt
from audit_engine.semantic_audit.evolution.replay import ReplayStatus, rebase_verification_obligation, replay_analysis
from audit_engine.semantic_audit.evolution.reverification import PriorityBand, ReverificationAction, ReverificationTask
from audit_engine.semantic_audit.evolution.service import GraphEvolutionResult
from audit_engine.semantic_audit.graph.analysis.identity import deterministic_id, graph_fingerprint
from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.graph.analysis.results import GraphAnalysisResult
from audit_engine.semantic_audit.orchestration import (
    AdaptiveOrchestrationSessionResult,
    AdaptiveReplanningPolicy,
    AuditBudget,
    OperationalPriority,
    OrchestrationPlan,
    OrchestrationPolicy,
    VerificationObjective,
    VerifierProfileCatalog,
    build_orchestration_plan,
    run_adaptive_orchestration,
)
from audit_engine.semantic_audit.verification import VerificationObligation, VerificationReceipt, VerificationService, VerifierRegistry


REVERIFICATION_ORCHESTRATION_PREPARATION_SCHEMA_VERSION = (
    "semantic_reverification_orchestration_preparation/v1"
)
REVERIFICATION_ORCHESTRATION_RECONCILIATION_SCHEMA_VERSION = (
    "semantic_reverification_orchestration_reconciliation/v1"
)
REVERIFICATION_ORCHESTRATION_RESULT_SCHEMA_VERSION = (
    "semantic_budget_aware_reverification/v1"
)
REVERIFICATION_ORCHESTRATION_BRIDGE_POLICY_VERSION = (
    "reverification_orchestration_bridge_policy/v1"
)

_AFFIRMATIVE_EVIDENCE_STATES = {
    VerificationStatus.OBSERVED,
    VerificationStatus.CORROBORATED,
    VerificationStatus.VALIDATED,
}


class BridgeTaskStatus(str, Enum):
    PREPARED = "prepared"
    NOT_APPLICABLE = "not_applicable"
    BLOCKED = "blocked"
    NON_VERIFICATION_TASK = "non_verification_task"


class OrchestratedReceiptStatus(str, Enum):
    RECONCILED = "reconciled"
    UNSATISFIED = "unsatisfied"
    NOT_APPLICABLE = "not_applicable"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ReverificationOrchestrationBridgePolicy:
    """Explicit semantics for translating G3.2 work into G3.3 objectives.

    Version 1 preserves the verifier restrictions already present on the
    rebased obligation.  It never broadens a historical verifier request.
    Substitution/equivalence requires a future explicit contract.
    """

    version: str = REVERIFICATION_ORCHESTRATION_BRIDGE_POLICY_VERSION
    fallback_minimum_evidence_state: VerificationStatus = VerificationStatus.VALIDATED
    preserve_prior_affirmative_evidence_state: bool = True
    preserve_requested_verifiers: bool = True

    def __post_init__(self) -> None:
        if self.fallback_minimum_evidence_state not in _AFFIRMATIVE_EVIDENCE_STATES:
            raise ValueError("fallback_minimum_evidence_state must be an affirmative evidence state.")
        if not self.preserve_requested_verifiers:
            raise ValueError(
                "G3.3.2 does not authorize verifier substitution; "
                "preserve_requested_verifiers must remain true."
            )

    def minimum_evidence_for(self, receipt: VerificationReceipt) -> VerificationStatus:
        if (
            self.preserve_prior_affirmative_evidence_state
            and receipt.evidence_state in _AFFIRMATIVE_EVIDENCE_STATES
        ):
            return receipt.evidence_state
        return self.fallback_minimum_evidence_state

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "fallback_minimum_evidence_state": self.fallback_minimum_evidence_state.value,
            "preserve_prior_affirmative_evidence_state": self.preserve_prior_affirmative_evidence_state,
            "preserve_requested_verifiers": self.preserve_requested_verifiers,
        }


_PRIORITY_MAP = {
    PriorityBand.CRITICAL: OperationalPriority.CRITICAL,
    PriorityBand.HIGH: OperationalPriority.HIGH,
    PriorityBand.NORMAL: OperationalPriority.NORMAL,
    PriorityBand.LOW: OperationalPriority.LOW,
}


@dataclass(frozen=True)
class ReverificationObjectiveBinding:
    task_id: str
    predecessor_receipt_id: str
    predecessor_obligation_id: str
    successor_obligation_id: str
    source_analysis_id: str
    objective_id: str
    priority: OperationalPriority
    minimum_evidence_state: VerificationStatus
    requested_verifier_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "predecessor_receipt_id": self.predecessor_receipt_id,
            "predecessor_obligation_id": self.predecessor_obligation_id,
            "successor_obligation_id": self.successor_obligation_id,
            "source_analysis_id": self.source_analysis_id,
            "objective_id": self.objective_id,
            "priority": self.priority.value,
            "minimum_evidence_state": self.minimum_evidence_state.value,
            "requested_verifier_ids": list(self.requested_verifier_ids),
        }


@dataclass(frozen=True)
class BridgeTaskRecord:
    task_id: str
    artifact_type: str
    artifact_id: str
    action: ReverificationAction
    status: BridgeTaskStatus
    reason: str
    successor_artifact_id: str | None = None
    objective_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "artifact_type": self.artifact_type,
            "artifact_id": self.artifact_id,
            "action": self.action.value,
            "status": self.status.value,
            "reason": self.reason,
            "successor_artifact_id": self.successor_artifact_id,
            "objective_id": self.objective_id,
        }


@dataclass(frozen=True)
class ReverificationOrchestrationPreparation:
    preparation_id: str
    reverification_plan_id: str
    before_snapshot_id: str
    after_snapshot_id: str
    bridge_policy_version: str
    analyses: tuple[GraphAnalysisResult, ...]
    obligations: tuple[VerificationObligation, ...]
    objectives: tuple[VerificationObjective, ...]
    bindings: tuple[ReverificationObjectiveBinding, ...]
    task_records: tuple[BridgeTaskRecord, ...]
    schema_version: str = REVERIFICATION_ORCHESTRATION_PREPARATION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "preparation_id": self.preparation_id,
            "reverification_plan_id": self.reverification_plan_id,
            "before_snapshot_id": self.before_snapshot_id,
            "after_snapshot_id": self.after_snapshot_id,
            "bridge_policy_version": self.bridge_policy_version,
            "analyses": [item.to_dict() for item in self.analyses],
            "obligations": [item.to_dict() for item in self.obligations],
            "objectives": [item.to_dict() for item in self.objectives],
            "bindings": [item.to_dict() for item in self.bindings],
            "task_records": [item.to_dict() for item in self.task_records],
        }


@dataclass(frozen=True)
class OrchestratedReceiptReconciliation:
    task_id: str
    objective_id: str | None
    predecessor_receipt_id: str
    status: OrchestratedReceiptStatus
    reason: str
    successor_receipt_id: str | None = None
    artifact_reconciliation: ArtifactReconciliation | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "objective_id": self.objective_id,
            "predecessor_receipt_id": self.predecessor_receipt_id,
            "status": self.status.value,
            "reason": self.reason,
            "successor_receipt_id": self.successor_receipt_id,
            "artifact_reconciliation": (
                self.artifact_reconciliation.to_dict()
                if self.artifact_reconciliation is not None
                else None
            ),
        }


@dataclass(frozen=True)
class ReverificationOrchestrationReconciliation:
    reconciliation_id: str
    preparation_id: str
    orchestration_session_id: str
    items: tuple[OrchestratedReceiptReconciliation, ...]
    successor_receipts: tuple[VerificationReceipt, ...]
    unresolved_task_ids: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = REVERIFICATION_ORCHESTRATION_RECONCILIATION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "reconciliation_id": self.reconciliation_id,
            "preparation_id": self.preparation_id,
            "orchestration_session_id": self.orchestration_session_id,
            "unresolved_task_ids": list(self.unresolved_task_ids),
            "items": [item.to_dict() for item in self.items],
            "successor_receipts": [item.to_dict() for item in self.successor_receipts],
        }


@dataclass(frozen=True)
class BudgetAwareReverificationResult:
    result_id: str
    preparation: ReverificationOrchestrationPreparation
    initial_plan: OrchestrationPlan
    session: AdaptiveOrchestrationSessionResult
    reconciliation: ReverificationOrchestrationReconciliation
    schema_version: str = REVERIFICATION_ORCHESTRATION_RESULT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "result_id": self.result_id,
            "preparation": self.preparation.to_dict(),
            "initial_plan": self.initial_plan.to_dict(),
            "session": self.session.to_dict(),
            "reconciliation": self.reconciliation.to_dict(),
        }


def _validate_bridge_inputs(
    *,
    evolution: GraphEvolutionResult,
    assessment: IncrementalReverificationResult,
    catalog: ReverificationReplayCatalog,
    after_graph: SemanticGraph,
) -> None:
    plan = assessment.reverification_plan
    if plan.before_snapshot_id != evolution.before_snapshot.snapshot_id:
        raise ValueError("Re-verification plan is bound to a different before snapshot.")
    if plan.after_snapshot_id != evolution.after_snapshot.snapshot_id:
        raise ValueError("Re-verification plan is bound to a different after snapshot.")
    if assessment.impact_report.before_snapshot_id != plan.before_snapshot_id:
        raise ValueError("Impact report and plan disagree on before snapshot.")
    if assessment.impact_report.after_snapshot_id != plan.after_snapshot_id:
        raise ValueError("Impact report and plan disagree on after snapshot.")
    if graph_fingerprint(after_graph) != evolution.after_snapshot.graph_fingerprint:
        raise ValueError("Bridge graph does not match the plan after snapshot.")
    catalog.validate_for_plan(plan)


def _analysis_task_by_artifact(tasks: tuple[ReverificationTask, ...]) -> Mapping[str, ReverificationTask]:
    return {
        task.artifact_id: task
        for task in tasks
        if task.action is ReverificationAction.RERUN_ANALYSIS
    }


def prepare_reverification_orchestration(
    *,
    evolution: GraphEvolutionResult,
    assessment: IncrementalReverificationResult,
    catalog: ReverificationReplayCatalog,
    after_graph: SemanticGraph,
    policy: ReverificationOrchestrationBridgePolicy | None = None,
) -> ReverificationOrchestrationPreparation:
    """Replay prerequisite analysis intent and prepare receipt objectives.

    No verifier is executed here.  Historical verifier restrictions survive the
    obligation rebase exactly; version 1 does not infer verifier equivalence.
    """

    policy = policy or ReverificationOrchestrationBridgePolicy()
    _validate_bridge_inputs(
        evolution=evolution,
        assessment=assessment,
        catalog=catalog,
        after_graph=after_graph,
    )
    plan = assessment.reverification_plan
    analysis_tasks = _analysis_task_by_artifact(plan.tasks)

    successor_by_predecessor: dict[str, GraphAnalysisResult] = {}
    task_records: dict[str, BridgeTaskRecord] = {}
    analyses: list[GraphAnalysisResult] = []

    # Replay only the analyses explicitly required by the incremental plan.
    for task in sorted(
        (item for item in plan.tasks if item.action is ReverificationAction.RERUN_ANALYSIS),
        key=lambda item: item.artifact_id,
    ):
        predecessor = catalog.analyses[task.artifact_id]
        replay = replay_analysis(
            predecessor,
            graph=after_graph,
            semantic_context=evolution.after_snapshot.semantic_context,
        )
        if replay.status is ReplayStatus.REPLAYED:
            assert replay.analysis is not None
            successor_by_predecessor[predecessor.analysis_id] = replay.analysis
            analyses.append(replay.analysis)
            task_records[task.task_id] = BridgeTaskRecord(
                task.task_id,
                task.artifact_type,
                task.artifact_id,
                task.action,
                BridgeTaskStatus.PREPARED,
                replay.reason,
                successor_artifact_id=replay.analysis.analysis_id,
            )
        else:
            task_records[task.task_id] = BridgeTaskRecord(
                task.task_id,
                task.artifact_type,
                task.artifact_id,
                task.action,
                BridgeTaskStatus.NOT_APPLICABLE,
                replay.reason,
            )

    obligations: list[VerificationObligation] = []
    objectives: list[VerificationObjective] = []
    bindings: list[ReverificationObjectiveBinding] = []

    for task in sorted(plan.tasks, key=lambda item: (item.action.value, item.artifact_id)):
        if task.action is not ReverificationAction.REVERIFY_RECEIPT:
            task_records.setdefault(
                task.task_id,
                BridgeTaskRecord(
                    task.task_id,
                    task.artifact_type,
                    task.artifact_id,
                    task.action,
                    BridgeTaskStatus.NON_VERIFICATION_TASK,
                    "task_remains_outside_verification_orchestration",
                ),
            )
            continue

        predecessor = catalog.receipts[task.artifact_id]
        source_id = predecessor.source_analysis_id
        source_task = analysis_tasks.get(source_id)
        if source_task is not None:
            source_record = task_records[source_task.task_id]
            if source_record.status is BridgeTaskStatus.NOT_APPLICABLE:
                task_records[task.task_id] = BridgeTaskRecord(
                    task.task_id,
                    task.artifact_type,
                    task.artifact_id,
                    task.action,
                    BridgeTaskStatus.NOT_APPLICABLE,
                    f"source_analysis_not_applicable:{source_id}",
                )
                continue
            if source_record.status is not BridgeTaskStatus.PREPARED:
                task_records[task.task_id] = BridgeTaskRecord(
                    task.task_id,
                    task.artifact_type,
                    task.artifact_id,
                    task.action,
                    BridgeTaskStatus.BLOCKED,
                    f"source_analysis_not_prepared:{source_id}",
                )
                continue

        successor_analysis = successor_by_predecessor.get(source_id)
        if successor_analysis is None:
            old_analysis = catalog.analyses[source_id]
            if (
                old_analysis.graph_fingerprint == evolution.after_snapshot.graph_fingerprint
                and old_analysis.semantic_context.fingerprint
                == evolution.after_snapshot.semantic_context_fingerprint
            ):
                successor_analysis = old_analysis
            else:
                task_records[task.task_id] = BridgeTaskRecord(
                    task.task_id,
                    task.artifact_type,
                    task.artifact_id,
                    task.action,
                    BridgeTaskStatus.BLOCKED,
                    f"source_analysis_not_replayed:{source_id}",
                )
                continue

        old_obligation = catalog.obligations[predecessor.obligation_id]
        old_analysis = catalog.analyses[source_id]
        mode = catalog.selection_modes[old_obligation.obligation_id]
        rebased = rebase_verification_obligation(
            old_obligation,
            predecessor_analysis=old_analysis,
            successor_analysis=successor_analysis,
            selection_mode=mode,
        )
        if rebased.status is not ReplayStatus.REPLAYED:
            task_records[task.task_id] = BridgeTaskRecord(
                task.task_id,
                task.artifact_type,
                task.artifact_id,
                task.action,
                BridgeTaskStatus.NOT_APPLICABLE,
                rebased.reason,
            )
            continue

        obligation = rebased.obligation
        assert obligation is not None
        if policy.preserve_requested_verifiers:
            if obligation.requested_verifier_ids != old_obligation.requested_verifier_ids:
                raise AssertionError("Rebased obligation broadened verifier authority unexpectedly.")

        minimum_state = policy.minimum_evidence_for(predecessor)
        priority = _PRIORITY_MAP[task.priority_band]
        objective = VerificationObjective.create(
            obligation_id=obligation.obligation_id,
            minimum_evidence_state=minimum_state,
            priority=priority,
        )
        binding = ReverificationObjectiveBinding(
            task_id=task.task_id,
            predecessor_receipt_id=predecessor.receipt_id,
            predecessor_obligation_id=old_obligation.obligation_id,
            successor_obligation_id=obligation.obligation_id,
            source_analysis_id=successor_analysis.analysis_id,
            objective_id=objective.objective_id,
            priority=priority,
            minimum_evidence_state=minimum_state,
            requested_verifier_ids=obligation.requested_verifier_ids,
        )
        obligations.append(obligation)
        objectives.append(objective)
        bindings.append(binding)
        task_records[task.task_id] = BridgeTaskRecord(
            task.task_id,
            task.artifact_type,
            task.artifact_id,
            task.action,
            BridgeTaskStatus.PREPARED,
            rebased.reason,
            successor_artifact_id=obligation.obligation_id,
            objective_id=objective.objective_id,
        )

    analyses = sorted({item.analysis_id: item for item in analyses}.values(), key=lambda x: x.analysis_id)
    obligations.sort(key=lambda item: item.obligation_id)
    objectives.sort(key=lambda item: item.objective_id)
    bindings.sort(key=lambda item: item.task_id)
    records = tuple(task_records[key] for key in sorted(task_records))

    identity = {
        "reverification_plan_id": plan.plan_id,
        "before_snapshot_id": plan.before_snapshot_id,
        "after_snapshot_id": plan.after_snapshot_id,
        "bridge_policy_version": policy.version,
        "analysis_ids": [item.analysis_id for item in analyses],
        "obligation_ids": [item.obligation_id for item in obligations],
        "objective_ids": [item.objective_id for item in objectives],
        "bindings": [item.to_dict() for item in bindings],
        "task_records": [item.to_dict() for item in records],
    }
    return ReverificationOrchestrationPreparation(
        preparation_id=deterministic_id(
            "reverification-orchestration-preparation", identity, length=28
        ),
        reverification_plan_id=plan.plan_id,
        before_snapshot_id=plan.before_snapshot_id,
        after_snapshot_id=plan.after_snapshot_id,
        bridge_policy_version=policy.version,
        analyses=tuple(analyses),
        obligations=tuple(obligations),
        objectives=tuple(objectives),
        bindings=tuple(bindings),
        task_records=records,
    )


def _terminal_receipts_by_objective(
    session: AdaptiveOrchestrationSessionResult,
) -> dict[str, VerificationReceipt]:
    receipts_by_id: dict[str, VerificationReceipt] = {}
    for execution in session.executions:
        receipts_by_id.update({receipt.receipt_id: receipt for receipt in execution.receipts})

    result: dict[str, VerificationReceipt] = {}
    for execution in session.executions:
        for objective in execution.objective_results:
            if objective.terminal_receipt_id:
                receipt = receipts_by_id.get(objective.terminal_receipt_id)
                if receipt is None:
                    raise ValueError("Orchestration result references an unavailable receipt.")
                result[objective.objective_id] = receipt
    return result


def reconcile_reverification_orchestration(
    *,
    preparation: ReverificationOrchestrationPreparation,
    initial_plan: OrchestrationPlan,
    session: AdaptiveOrchestrationSessionResult,
    catalog: ReverificationReplayCatalog,
) -> ReverificationOrchestrationReconciliation:
    if session.initial_plan_id != initial_plan.plan_id:
        raise ValueError("Adaptive session is bound to a different initial plan.")
    planned_objectives = {
        route.objective.objective_id for route in initial_plan.routes
    }
    prepared_objectives = {item.objective_id for item in preparation.objectives}
    if planned_objectives != prepared_objectives:
        raise ValueError("Initial orchestration plan does not match prepared objectives.")

    terminal = _terminal_receipts_by_objective(session)
    binding_by_task = {item.task_id: item for item in preparation.bindings}
    items: list[OrchestratedReceiptReconciliation] = []
    successors: list[VerificationReceipt] = []
    unresolved: list[str] = []

    for record in preparation.task_records:
        if record.action is not ReverificationAction.REVERIFY_RECEIPT:
            continue
        binding = binding_by_task.get(record.task_id)
        predecessor = catalog.receipts[record.artifact_id]
        if record.status is BridgeTaskStatus.NOT_APPLICABLE:
            items.append(
                OrchestratedReceiptReconciliation(
                    record.task_id,
                    None,
                    predecessor.receipt_id,
                    OrchestratedReceiptStatus.NOT_APPLICABLE,
                    record.reason,
                )
            )
            continue
        if record.status is BridgeTaskStatus.BLOCKED:
            unresolved.append(record.task_id)
            items.append(
                OrchestratedReceiptReconciliation(
                    record.task_id,
                    None,
                    predecessor.receipt_id,
                    OrchestratedReceiptStatus.BLOCKED,
                    record.reason,
                )
            )
            continue
        if binding is None:
            raise ValueError("Prepared receipt task is missing its objective binding.")
        successor = terminal.get(binding.objective_id)
        if successor is None:
            unresolved.append(record.task_id)
            items.append(
                OrchestratedReceiptReconciliation(
                    record.task_id,
                    binding.objective_id,
                    predecessor.receipt_id,
                    OrchestratedReceiptStatus.UNSATISFIED,
                    f"orchestration_session_{session.status.value}",
                )
            )
            continue
        successors.append(successor)
        items.append(
            OrchestratedReceiptReconciliation(
                record.task_id,
                binding.objective_id,
                predecessor.receipt_id,
                OrchestratedReceiptStatus.RECONCILED,
                "terminal_receipt_satisfies_reverification_objective",
                successor_receipt_id=successor.receipt_id,
                artifact_reconciliation=reconcile_receipt(predecessor, successor),
            )
        )

    items.sort(key=lambda item: item.task_id)
    successors = sorted({item.receipt_id: item for item in successors}.values(), key=lambda x: x.receipt_id)
    unresolved = sorted(set(unresolved))
    identity = {
        "preparation_id": preparation.preparation_id,
        "orchestration_session_id": session.session_id,
        "items": [item.to_dict() for item in items],
        "successor_receipt_ids": [item.receipt_id for item in successors],
        "unresolved_task_ids": unresolved,
    }
    return ReverificationOrchestrationReconciliation(
        reconciliation_id=deterministic_id(
            "reverification-orchestration-reconciliation", identity, length=28
        ),
        preparation_id=preparation.preparation_id,
        orchestration_session_id=session.session_id,
        items=tuple(items),
        successor_receipts=tuple(successors),
        unresolved_task_ids=tuple(unresolved),
    )


def run_budget_aware_reverification(
    *,
    evolution: GraphEvolutionResult,
    assessment: IncrementalReverificationResult,
    catalog: ReverificationReplayCatalog,
    after_graph: SemanticGraph,
    verification_service: VerificationService,
    registry: VerifierRegistry,
    profiles: VerifierProfileCatalog,
    budget: AuditBudget,
    bridge_policy: ReverificationOrchestrationBridgePolicy | None = None,
    orchestration_policy: OrchestrationPolicy | None = None,
    adaptive_policy: AdaptiveReplanningPolicy | None = None,
) -> BudgetAwareReverificationResult:
    """Run the G3.2 receipt re-verification workload under G3.3 budgets.

    The result stops at successor verification receipts. Finding/rule
    reevaluation remains in the G3.2.2 lifecycle/reconciliation layer.
    """

    bridge_policy = bridge_policy or ReverificationOrchestrationBridgePolicy()
    orchestration_policy = orchestration_policy or OrchestrationPolicy()
    adaptive_policy = adaptive_policy or AdaptiveReplanningPolicy()

    preparation = prepare_reverification_orchestration(
        evolution=evolution,
        assessment=assessment,
        catalog=catalog,
        after_graph=after_graph,
        policy=bridge_policy,
    )
    obligations = {item.obligation_id: item for item in preparation.obligations}
    analyses = {item.analysis_id: item for item in preparation.analyses}
    # A receipt task may reuse an unchanged after-bound analysis that did not
    # need replay. Include those analyses explicitly for orchestration execution.
    for binding in preparation.bindings:
        if binding.source_analysis_id not in analyses:
            for analysis in catalog.analyses.values():
                if analysis.analysis_id == binding.source_analysis_id:
                    analyses[analysis.analysis_id] = analysis
                    break
    graphs = {analysis_id: after_graph for analysis_id in analyses}

    initial_plan = build_orchestration_plan(
        obligations=preparation.obligations,
        objectives=preparation.objectives,
        registry=registry,
        profiles=profiles,
        budget=budget,
        policy=orchestration_policy,
    )
    session = run_adaptive_orchestration(
        initial_plan=initial_plan,
        obligations=obligations,
        analysis_results=analyses,
        verification_service=verification_service,
        registry=registry,
        profiles=profiles,
        semantic_graphs=graphs,
        orchestration_policy=orchestration_policy,
        adaptive_policy=adaptive_policy,
    )
    reconciliation = reconcile_reverification_orchestration(
        preparation=preparation,
        initial_plan=initial_plan,
        session=session,
        catalog=catalog,
    )
    identity = {
        "preparation_id": preparation.preparation_id,
        "initial_plan_id": initial_plan.plan_id,
        "session_id": session.session_id,
        "reconciliation_id": reconciliation.reconciliation_id,
    }
    return BudgetAwareReverificationResult(
        result_id=deterministic_id("budget-aware-reverification", identity, length=28),
        preparation=preparation,
        initial_plan=initial_plan,
        session=session,
        reconciliation=reconciliation,
    )
