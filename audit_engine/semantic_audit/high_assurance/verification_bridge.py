"""Bridge controlled high-assurance executions into G3.1 verification receipts."""

from __future__ import annotations

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.verification.models import (
    VerificationAttempt,
    VerificationContext,
    VerificationDecision,
    VerificationObligation,
)
from audit_engine.semantic_audit.verification.verifier import VerifierDescriptor

from .execution import ControlledHighAssuranceExecutor
from .models import HighAssuranceExecutionStatus


class ControlledHighAssuranceVerifier:
    """Expose one high-assurance adapter through the standard Verifier protocol."""

    def __init__(self, executor: ControlledHighAssuranceExecutor, adapter_id: str) -> None:
        self.executor = executor
        self.adapter = executor.registry.require(adapter_id)
        d = self.adapter.descriptor
        self._descriptor = VerifierDescriptor(
            verifier_id=d.adapter_id,
            version=d.version,
            supported_obligation_types=d.supported_obligation_types,
        )

    @property
    def descriptor(self) -> VerifierDescriptor:
        return self._descriptor

    def verify(
        self,
        obligation: VerificationObligation,
        context: VerificationContext,
    ) -> VerificationAttempt:
        execution = self.executor.execute(
            obligation,
            context,
            adapter_id=self.descriptor.verifier_id,
        )
        details = {"high_assurance_execution": execution.to_dict()}
        if execution.status == HighAssuranceExecutionStatus.EXECUTED:
            assert execution.result is not None
            result = execution.result
            return VerificationAttempt.create(
                obligation_id=obligation.obligation_id,
                verifier_id=self.descriptor.verifier_id,
                verifier_version=self.descriptor.version,
                decision=result.decision,
                evidence_state=result.evidence_state,
                evidence_ids=obligation.evidence_ids,
                details=details,
                error=result.error,
            )
        return VerificationAttempt.create(
            obligation_id=obligation.obligation_id,
            verifier_id=self.descriptor.verifier_id,
            verifier_version=self.descriptor.version,
            decision=VerificationDecision.ERROR,
            evidence_state=VerificationStatus.PROPOSED,
            evidence_ids=obligation.evidence_ids,
            details=details,
            error=execution.denial_reason or execution.status.value,
        )
