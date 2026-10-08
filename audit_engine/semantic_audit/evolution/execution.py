"""Deterministic execution of incremental semantic re-verification plans."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph
from audit_engine.semantic_audit.findings.factory import FindingFactory
from audit_engine.semantic_audit.findings.models import AuditFinding
from audit_engine.semantic_audit.graph.analysis.identity import deterministic_id, graph_fingerprint
from audit_engine.semantic_audit.graph.analysis.results import GraphAnalysisResult
from audit_engine.semantic_audit.rules.domain_models import DomainRuleScope
from audit_engine.semantic_audit.rules.execution import DomainRuleExecutionResult
from audit_engine.semantic_audit.rules.evaluator import RuleEvaluator
from audit_engine.semantic_audit.rules.models import RuleDisposition, RuleEvaluationResult, SemanticAuditRule
from audit_engine.semantic_audit.verification import VerificationObligation, VerificationReceipt, VerificationService

from .incremental import IncrementalReverificationResult
from .reconciliation import (
    ArtifactReconciliation,
    blocked_reconciliation,
    failed_reconciliation,
    reconcile_analysis,
    reconcile_finding,
    reconcile_receipt,
    target_absent_reconciliation,
)
from .replay import ReplaySelectionMode, ReplayStatus, rebase_verification_obligation, replay_analysis
from .reverification import ReverificationAction, ReverificationPlan
from .service import GraphEvolutionResult


REVERIFICATION_EXECUTION_SCHEMA_VERSION = "semantic_reverification_execution/v1"


class TaskExecutionStatus(str, Enum):
    COMPLETED = "completed"
    NOT_APPLICABLE = "not_applicable"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class ReverificationTaskExecution:
    task_id: str
    artifact_type: str
    predecessor_artifact_id: str
    action: ReverificationAction
    status: TaskExecutionStatus
    successor_artifact_id: str | None
    message: str
    reconciliation: ArtifactReconciliation

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "artifact_type": self.artifact_type,
            "predecessor_artifact_id": self.predecessor_artifact_id,
            "successor_artifact_id": self.successor_artifact_id,
            "action": self.action.value,
            "status": self.status.value,
            "message": self.message,
            "reconciliation": self.reconciliation.to_dict(),
        }


@dataclass(frozen=True)
class ArtifactReplacement:
    artifact_type: str
    predecessor_artifact_id: str
    successor_artifact_id: str

    def to_dict(self) -> dict[str, str]:
        return {
            "artifact_type": self.artifact_type,
            "predecessor_artifact_id": self.predecessor_artifact_id,
            "successor_artifact_id": self.successor_artifact_id,
        }


@dataclass(frozen=True)
class ReverificationExecutionResult:
    execution_id: str
    plan_id: str
    before_snapshot_id: str
    after_snapshot_id: str
    task_executions: tuple[ReverificationTaskExecution, ...]
    replacements: tuple[ArtifactReplacement, ...]
    analyses: tuple[GraphAnalysisResult, ...] = field(default_factory=tuple)
    obligations: tuple[VerificationObligation, ...] = field(default_factory=tuple)
    receipts: tuple[VerificationReceipt, ...] = field(default_factory=tuple)
    evaluations: tuple[RuleEvaluationResult, ...] = field(default_factory=tuple)
    findings: tuple[AuditFinding, ...] = field(default_factory=tuple)
    schema_version: str = REVERIFICATION_EXECUTION_SCHEMA_VERSION

    @property
    def succeeded(self) -> bool:
        return all(
            item.status in (TaskExecutionStatus.COMPLETED, TaskExecutionStatus.NOT_APPLICABLE)
            for item in self.task_executions
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "execution_id": self.execution_id,
            "plan_id": self.plan_id,
            "before_snapshot_id": self.before_snapshot_id,
            "after_snapshot_id": self.after_snapshot_id,
            "succeeded": self.succeeded,
            "task_executions": [item.to_dict() for item in self.task_executions],
            "replacements": [item.to_dict() for item in self.replacements],
            "analyses": [item.to_dict() for item in self.analyses],
            "obligations": [item.to_dict() for item in self.obligations],
            "receipts": [item.to_dict() for item in self.receipts],
            "evaluations": [item.to_dict() for item in self.evaluations],
            "findings": [item.to_dict() for item in self.findings],
        }


class ReverificationReplayCatalog:
    """Caller-supplied historical artifacts and explicit replay semantics."""

    def __init__(self) -> None:
        self.analyses: dict[str, GraphAnalysisResult] = {}
        self.obligations: dict[str, VerificationObligation] = {}
        self.receipts: dict[str, VerificationReceipt] = {}
        self.findings: dict[str, AuditFinding] = {}
        self.rules: dict[tuple[str, str], SemanticAuditRule] = {}
        self.selection_modes: dict[str, ReplaySelectionMode] = {}

    @staticmethod
    def _insert(mapping, key, value, label: str) -> None:
        existing = mapping.get(key)
        if existing is not None and existing != value:
            raise ValueError(f"{label.capitalize()} identity collision: {key}")
        mapping[key] = value

    def add_analysis(self, value: GraphAnalysisResult) -> None:
        self._insert(self.analyses, value.analysis_id, value, "analysis")

    def add_obligation(
        self,
        value: VerificationObligation,
        *,
        selection_mode: ReplaySelectionMode = ReplaySelectionMode.EXACT_IDS,
    ) -> None:
        self._insert(self.obligations, value.obligation_id, value, "obligation")
        existing = self.selection_modes.get(value.obligation_id)
        if existing is not None and existing is not selection_mode:
            raise ValueError(f"Conflicting replay selection mode for {value.obligation_id}.")
        self.selection_modes[value.obligation_id] = selection_mode

    def add_receipt(self, value: VerificationReceipt) -> None:
        self._insert(self.receipts, value.receipt_id, value, "receipt")

    def add_finding(self, value: AuditFinding) -> None:
        self._insert(self.findings, value.finding_id, value, "finding")

    def add_rule(self, value: SemanticAuditRule) -> None:
        self._insert(self.rules, (value.rule_id, value.version), value, "rule")

    def add_domain_execution(self, *, analysis, rule, execution: DomainRuleExecutionResult) -> None:
        self.add_analysis(analysis)
        self.add_rule(rule.policy)
        mode = (
            ReplaySelectionMode.OBSERVATION_SEMANTICS
            if rule.selector.scope is DomainRuleScope.OBSERVATION
            else ReplaySelectionMode.ANALYSIS_SCOPE
        )
        for obligation in execution.obligations:
            self.add_obligation(obligation, selection_mode=mode)
        for receipt in execution.receipts:
            self.add_receipt(receipt)
        for finding in execution.findings:
            self.add_finding(finding)

    def validate_for_plan(self, plan: ReverificationPlan) -> None:
        errors: list[str] = []
        for task in plan.tasks:
            if task.action is ReverificationAction.RERUN_ANALYSIS:
                if task.artifact_id not in self.analyses:
                    errors.append(f"missing analysis:{task.artifact_id}")
            elif task.action is ReverificationAction.REVERIFY_RECEIPT:
                receipt = self.receipts.get(task.artifact_id)
                if receipt is None:
                    errors.append(f"missing receipt:{task.artifact_id}")
                    continue
                if receipt.obligation_id not in self.obligations:
                    errors.append(f"missing obligation:{receipt.obligation_id}")
                if receipt.source_analysis_id not in self.analyses:
                    errors.append(f"missing source analysis:{receipt.source_analysis_id}")
            elif task.action is ReverificationAction.REEVALUATE_FINDING:
                finding = self.findings.get(task.artifact_id)
                if finding is None:
                    errors.append(f"missing finding:{task.artifact_id}")
                    continue
                if finding.receipt_id not in self.receipts:
                    errors.append(f"missing finding receipt:{finding.receipt_id}")
                if (finding.rule_id, finding.rule_version) not in self.rules:
                    errors.append(f"missing rule:{finding.rule_id}@{finding.rule_version}")
        if errors:
            raise ValueError("Replay catalog is incomplete for plan: " + "; ".join(sorted(set(errors))))


class IncrementalReverificationExecutor:
    """Execute already-planned work; never invent tasks or persist implicitly."""

    def __init__(self, verification_service: VerificationService) -> None:
        self.verification_service = verification_service
        self.rule_evaluator = RuleEvaluator()

    def execute(
        self,
        *,
        evolution: GraphEvolutionResult,
        assessment: IncrementalReverificationResult,
        catalog: ReverificationReplayCatalog,
        after_graph: SemanticGraph,
    ) -> ReverificationExecutionResult:
        plan = assessment.reverification_plan
        self._validate_inputs(evolution, assessment, plan, catalog, after_graph)

        pending = {task.artifact_id: task for task in plan.tasks}
        task_status: dict[str, ReverificationTaskExecution] = {}
        successor_analyses: dict[str, GraphAnalysisResult] = {}
        successor_obligations: dict[str, VerificationObligation] = {}
        successor_receipts: dict[str, VerificationReceipt] = {}

        analyses: list[GraphAnalysisResult] = []
        obligations: list[VerificationObligation] = []
        receipts: list[VerificationReceipt] = []
        evaluations: list[RuleEvaluationResult] = []
        findings: list[AuditFinding] = []
        executions: list[ReverificationTaskExecution] = []
        replacements: list[ArtifactReplacement] = []

        while pending:
            runnable = [
                task for task in pending.values()
                if not any(prereq in pending for prereq in task.prerequisite_artifact_ids)
            ]
            if not runnable:
                raise ValueError("Re-verification plan contains a prerequisite cycle.")
            runnable.sort(key=lambda item: (self._action_rank(item.action), item.artifact_id))
            for task in runnable:
                try:
                    if task.action is ReverificationAction.RERUN_ANALYSIS:
                        record = self._execute_analysis(
                            task, catalog, after_graph, evolution,
                            successor_analyses, analyses, replacements,
                        )
                    elif task.action is ReverificationAction.REVERIFY_RECEIPT:
                        record = self._execute_receipt(
                            task, catalog, after_graph, evolution, task_status,
                            successor_analyses, successor_obligations, successor_receipts,
                            obligations, receipts, replacements,
                        )
                    elif task.action is ReverificationAction.REEVALUATE_FINDING:
                        record = self._execute_finding(
                            task, catalog, task_status, successor_obligations,
                            successor_receipts, evaluations, findings, replacements,
                        )
                    else:
                        raise ValueError(f"Unsupported re-verification action: {task.action!r}")
                except Exception as exc:
                    record = ReverificationTaskExecution(
                        task.task_id, task.artifact_type, task.artifact_id, task.action,
                        TaskExecutionStatus.FAILED, None, str(exc),
                        failed_reconciliation(task.artifact_type, task.artifact_id, str(exc)),
                    )
                executions.append(record)
                task_status[task.artifact_id] = record
                pending.pop(task.artifact_id)

        identity = {
            "plan_id": plan.plan_id,
            "before_snapshot_id": evolution.before_snapshot.snapshot_id,
            "after_snapshot_id": evolution.after_snapshot.snapshot_id,
            "task_executions": [item.to_dict() for item in executions],
            "replacements": [item.to_dict() for item in replacements],
        }
        return ReverificationExecutionResult(
            execution_id=deterministic_id("reverification-execution", identity, length=28),
            plan_id=plan.plan_id,
            before_snapshot_id=evolution.before_snapshot.snapshot_id,
            after_snapshot_id=evolution.after_snapshot.snapshot_id,
            task_executions=tuple(executions),
            replacements=tuple(replacements),
            analyses=tuple(analyses),
            obligations=tuple(obligations),
            receipts=tuple(receipts),
            evaluations=tuple(evaluations),
            findings=tuple(findings),
        )

    @staticmethod
    def _action_rank(action: ReverificationAction) -> int:
        return {
            ReverificationAction.RERUN_ANALYSIS: 0,
            ReverificationAction.REVERIFY_RECEIPT: 1,
            ReverificationAction.REEVALUATE_FINDING: 2,
        }[action]

    @staticmethod
    def _validate_inputs(evolution, assessment, plan, catalog, after_graph) -> None:
        if plan.before_snapshot_id != evolution.before_snapshot.snapshot_id:
            raise ValueError("Re-verification plan is bound to a different before snapshot.")
        if plan.after_snapshot_id != evolution.after_snapshot.snapshot_id:
            raise ValueError("Re-verification plan is bound to a different after snapshot.")
        if assessment.impact_report.before_snapshot_id != plan.before_snapshot_id:
            raise ValueError("Impact report and plan disagree on before snapshot.")
        if assessment.impact_report.after_snapshot_id != plan.after_snapshot_id:
            raise ValueError("Impact report and plan disagree on after snapshot.")
        if graph_fingerprint(after_graph) != evolution.after_snapshot.graph_fingerprint:
            raise ValueError("Execution graph does not match the plan after snapshot.")
        catalog.validate_for_plan(plan)

    def _execute_analysis(self, task, catalog, after_graph, evolution, successor_analyses, analyses, replacements):
        predecessor = catalog.analyses[task.artifact_id]
        replay = replay_analysis(
            predecessor,
            graph=after_graph,
            semantic_context=evolution.after_snapshot.semantic_context,
        )
        if replay.status is not ReplayStatus.REPLAYED:
            return ReverificationTaskExecution(
                task.task_id, "analysis", predecessor.analysis_id, task.action,
                TaskExecutionStatus.NOT_APPLICABLE, None, replay.reason,
                target_absent_reconciliation("analysis", predecessor.analysis_id, replay.reason),
            )
        successor = replay.analysis
        assert successor is not None
        successor_analyses[predecessor.analysis_id] = successor
        analyses.append(successor)
        replacements.append(ArtifactReplacement("analysis", predecessor.analysis_id, successor.analysis_id))
        return ReverificationTaskExecution(
            task.task_id, "analysis", predecessor.analysis_id, task.action,
            TaskExecutionStatus.COMPLETED, successor.analysis_id, "analysis_replayed",
            reconcile_analysis(predecessor, successor),
        )

    def _execute_receipt(
        self, task, catalog, after_graph, evolution, task_status,
        successor_analyses, successor_obligations, successor_receipts,
        obligations, receipts, replacements,
    ):
        predecessor = catalog.receipts[task.artifact_id]
        source_id = predecessor.source_analysis_id
        upstream = task_status.get(source_id)
        if upstream is not None and upstream.status is TaskExecutionStatus.NOT_APPLICABLE:
            reason = f"source_analysis_not_applicable:{source_id}"
            return ReverificationTaskExecution(
                task.task_id, "verification_receipt", predecessor.receipt_id, task.action,
                TaskExecutionStatus.NOT_APPLICABLE, None, reason,
                target_absent_reconciliation("verification_receipt", predecessor.receipt_id, reason),
            )
        if upstream is not None and upstream.status is not TaskExecutionStatus.COMPLETED:
            reason = f"source_analysis_{upstream.status.value}:{source_id}"
            return ReverificationTaskExecution(
                task.task_id, "verification_receipt", predecessor.receipt_id, task.action,
                TaskExecutionStatus.BLOCKED, None, reason,
                blocked_reconciliation("verification_receipt", predecessor.receipt_id, reason),
            )

        successor_analysis = successor_analyses.get(source_id)
        if successor_analysis is None:
            old_analysis = catalog.analyses[source_id]
            if (
                old_analysis.graph_fingerprint == evolution.after_snapshot.graph_fingerprint
                and old_analysis.semantic_context.fingerprint == evolution.after_snapshot.semantic_context_fingerprint
            ):
                successor_analysis = old_analysis
            else:
                reason = f"source_analysis_not_replayed:{source_id}"
                return ReverificationTaskExecution(
                    task.task_id, "verification_receipt", predecessor.receipt_id, task.action,
                    TaskExecutionStatus.BLOCKED, None, reason,
                    blocked_reconciliation("verification_receipt", predecessor.receipt_id, reason),
                )

        old_obligation = catalog.obligations[predecessor.obligation_id]
        old_analysis = catalog.analyses[source_id]
        mode = catalog.selection_modes.get(old_obligation.obligation_id, ReplaySelectionMode.EXACT_IDS)
        rebased = rebase_verification_obligation(
            old_obligation,
            predecessor_analysis=old_analysis,
            successor_analysis=successor_analysis,
            selection_mode=mode,
        )
        if rebased.status is not ReplayStatus.REPLAYED:
            return ReverificationTaskExecution(
                task.task_id, "verification_receipt", predecessor.receipt_id, task.action,
                TaskExecutionStatus.NOT_APPLICABLE, None, rebased.reason,
                target_absent_reconciliation("verification_receipt", predecessor.receipt_id, rebased.reason),
            )

        obligation = rebased.obligation
        assert obligation is not None
        receipt = self.verification_service.verify(
            obligation,
            successor_analysis,
            verifier_id=predecessor.verifier_id,
            semantic_graph=after_graph,
        )
        successor_obligations[old_obligation.obligation_id] = obligation
        successor_receipts[predecessor.receipt_id] = receipt
        obligations.append(obligation)
        receipts.append(receipt)
        replacements.append(ArtifactReplacement("verification_receipt", predecessor.receipt_id, receipt.receipt_id))
        return ReverificationTaskExecution(
            task.task_id, "verification_receipt", predecessor.receipt_id, task.action,
            TaskExecutionStatus.COMPLETED, receipt.receipt_id, "verification_replayed",
            reconcile_receipt(predecessor, receipt),
        )

    def _execute_finding(
        self, task, catalog, task_status, successor_obligations,
        successor_receipts, evaluations, findings, replacements,
    ):
        predecessor = catalog.findings[task.artifact_id]
        upstream = task_status.get(predecessor.receipt_id)
        if upstream is not None and upstream.status is TaskExecutionStatus.NOT_APPLICABLE:
            reason = f"receipt_target_no_longer_present:{predecessor.receipt_id}"
            return ReverificationTaskExecution(
                task.task_id, "finding", predecessor.finding_id, task.action,
                TaskExecutionStatus.NOT_APPLICABLE, None, reason,
                target_absent_reconciliation("finding", predecessor.finding_id, reason),
            )
        if upstream is not None and upstream.status is not TaskExecutionStatus.COMPLETED:
            reason = f"receipt_{upstream.status.value}:{predecessor.receipt_id}"
            return ReverificationTaskExecution(
                task.task_id, "finding", predecessor.finding_id, task.action,
                TaskExecutionStatus.BLOCKED, None, reason,
                blocked_reconciliation("finding", predecessor.finding_id, reason),
            )

        old_receipt = catalog.receipts[predecessor.receipt_id]
        old_obligation = catalog.obligations[old_receipt.obligation_id]
        receipt = successor_receipts.get(predecessor.receipt_id)
        obligation = successor_obligations.get(old_obligation.obligation_id)
        if receipt is None or obligation is None:
            reason = "finding_prerequisite_not_replayed"
            return ReverificationTaskExecution(
                task.task_id, "finding", predecessor.finding_id, task.action,
                TaskExecutionStatus.BLOCKED, None, reason,
                blocked_reconciliation("finding", predecessor.finding_id, reason),
            )

        rule = catalog.rules[(predecessor.rule_id, predecessor.rule_version)]
        evaluation = self.rule_evaluator.evaluate(rule, obligation, receipt)
        evaluations.append(evaluation)
        successor = None
        if evaluation.disposition is RuleDisposition.TRIGGERED:
            successor = FindingFactory.create(rule, evaluation, receipt)
            findings.append(successor)
            replacements.append(ArtifactReplacement("finding", predecessor.finding_id, successor.finding_id))
        return ReverificationTaskExecution(
            task.task_id, "finding", predecessor.finding_id, task.action,
            TaskExecutionStatus.COMPLETED, successor.finding_id if successor else None,
            "finding_rule_reevaluated",
            reconcile_finding(predecessor, disposition=evaluation.disposition, successor=successor),
        )
