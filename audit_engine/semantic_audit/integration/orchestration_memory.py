"""Explicit audit-memory commit for G3.3.2 orchestration integration artifacts."""

from __future__ import annotations

from dataclasses import dataclass

from audit_engine.semantic_audit.evolution.memory import AuditLongTermMemory, MemoryRecord

from .reverification_orchestration import BudgetAwareReverificationResult


@dataclass(frozen=True)
class OrchestrationIntegrationMemoryCommit:
    result_id: str
    snapshot_id: str
    record_ids: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "result_id": self.result_id,
            "snapshot_id": self.snapshot_id,
            "record_ids": list(self.record_ids),
        }


class OrchestrationIntegrationMemoryRecorder:
    """Persist orchestration integration artifacts only when explicitly called."""

    def record(
        self,
        *,
        memory: AuditLongTermMemory,
        result: BudgetAwareReverificationResult,
        snapshot_id: str,
    ) -> OrchestrationIntegrationMemoryCommit:
        if snapshot_id != result.preparation.after_snapshot_id:
            raise ValueError("Orchestration result must be recorded against its after snapshot.")

        records: list[MemoryRecord] = []

        def append(artifact_type: str, artifact_id: str, payload: dict) -> None:
            records.append(
                memory.append_artifact(
                    artifact_type=artifact_type,
                    artifact_id=artifact_id,
                    snapshot_id=snapshot_id,
                    payload=payload,
                )
            )

        append(
            "reverification_orchestration_preparation",
            result.preparation.preparation_id,
            result.preparation.to_dict(),
        )
        append("orchestration_plan", result.initial_plan.plan_id, result.initial_plan.to_dict())
        append(
            "adaptive_orchestration_session",
            result.session.session_id,
            result.session.to_dict(),
        )
        append(
            "reverification_orchestration_reconciliation",
            result.reconciliation.reconciliation_id,
            result.reconciliation.to_dict(),
        )
        append("budget_aware_reverification", result.result_id, result.to_dict())

        for analysis in result.preparation.analyses:
            append("analysis", analysis.analysis_id, analysis.to_dict())
        for obligation in result.preparation.obligations:
            append("verification_obligation", obligation.obligation_id, obligation.to_dict())
        for execution in result.session.executions:
            append("orchestration_execution", execution.execution_id, execution.to_dict())
        for replan in result.session.replans:
            append("adaptive_orchestration_replan", replan.replan_id, replan.to_dict())
            if replan.continuation_plan is not None:
                append(
                    "orchestration_plan",
                    replan.continuation_plan.plan_id,
                    replan.continuation_plan.to_dict(),
                )
        for receipt in result.reconciliation.successor_receipts:
            append("verification_receipt", receipt.receipt_id, receipt.to_dict())

        return OrchestrationIntegrationMemoryCommit(
            result.result_id,
            snapshot_id,
            tuple(record.record_id for record in records),
        )
