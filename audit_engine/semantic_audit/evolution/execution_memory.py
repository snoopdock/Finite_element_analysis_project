"""Explicit persistence of G3.2.2 re-verification execution artifacts."""

from __future__ import annotations

from dataclasses import dataclass

from .execution import ReverificationExecutionResult
from .memory import AuditLongTermMemory, MemoryRecord


@dataclass(frozen=True)
class ExecutionMemoryCommit:
    execution_id: str
    snapshot_id: str
    record_ids: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "execution_id": self.execution_id,
            "snapshot_id": self.snapshot_id,
            "record_ids": list(self.record_ids),
        }


class ReverificationExecutionMemoryRecorder:
    """Append successor artifacts only when explicitly invoked by the caller."""

    def record(
        self,
        *,
        memory: AuditLongTermMemory,
        result: ReverificationExecutionResult,
        snapshot_id: str,
    ) -> ExecutionMemoryCommit:
        if snapshot_id != result.after_snapshot_id:
            raise ValueError("Execution result must be recorded against its after snapshot.")

        records: list[MemoryRecord] = [
            memory.append_artifact(
                artifact_type="reverification_execution",
                artifact_id=result.execution_id,
                snapshot_id=snapshot_id,
                payload=result.to_dict(),
            )
        ]
        for analysis in result.analyses:
            records.append(memory.append_artifact(
                artifact_type="analysis", artifact_id=analysis.analysis_id,
                snapshot_id=snapshot_id, payload=analysis.to_dict(),
            ))
        for obligation in result.obligations:
            records.append(memory.append_artifact(
                artifact_type="verification_obligation", artifact_id=obligation.obligation_id,
                snapshot_id=snapshot_id, payload=obligation.to_dict(),
            ))
        for receipt in result.receipts:
            records.append(memory.append_artifact(
                artifact_type="verification_receipt", artifact_id=receipt.receipt_id,
                snapshot_id=snapshot_id, payload=receipt.to_dict(),
            ))
        for finding in result.findings:
            records.append(memory.append_artifact(
                artifact_type="finding", artifact_id=finding.finding_id,
                snapshot_id=snapshot_id, payload=finding.to_dict(),
            ))
        return ExecutionMemoryCommit(
            result.execution_id,
            snapshot_id,
            tuple(record.record_id for record in records),
        )
