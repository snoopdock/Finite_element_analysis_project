"""Controlled execution boundary for high-assurance adapters."""

from __future__ import annotations

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.verification.models import VerificationContext, VerificationObligation

from .models import (
    HighAssuranceExecutionRecord,
    HighAssuranceExecutionStatus,
    HighAssuranceRequest,
    ValidationCompleteness,
)
from .policy import HighAssurancePolicy
from .registry import HighAssuranceAdapterRegistry


class ControlledHighAssuranceExecutor:
    """Execute only pre-registered adapters allowed by an explicit policy.

    This class deliberately contains no shell/subprocess/network execution API.
    Such mechanisms require future, dedicated sandbox adapters.
    """

    def __init__(
        self,
        registry: HighAssuranceAdapterRegistry,
        *,
        policy: HighAssurancePolicy | None = None,
    ) -> None:
        self.registry = registry
        self.policy = policy or HighAssurancePolicy()

    def prepare_request(
        self,
        obligation: VerificationObligation,
        context: VerificationContext,
        *,
        adapter_id: str,
    ) -> HighAssuranceRequest:
        context.validate_obligation_binding(obligation)
        adapter = self.registry.require(adapter_id)
        descriptor = adapter.descriptor
        if obligation.obligation_type not in descriptor.supported_obligation_types:
            raise ValueError(
                f"Adapter {adapter_id} does not support obligation type {obligation.obligation_type}."
            )
        timeout_ms = int(obligation.parameters.get("timeout_ms", self.policy.max_timeout_ms))
        return HighAssuranceRequest.create(
            obligation_id=obligation.obligation_id,
            adapter_id=adapter_id,
            mechanism=descriptor.mechanism,
            graph_fingerprint=obligation.graph_fingerprint,
            semantic_context_fingerprint=obligation.semantic_context_fingerprint,
            timeout_ms=timeout_ms,
            parameters=obligation.parameters,
        )

    def execute(
        self,
        obligation: VerificationObligation,
        context: VerificationContext,
        *,
        adapter_id: str,
    ) -> HighAssuranceExecutionRecord:
        request = self.prepare_request(obligation, context, adapter_id=adapter_id)
        adapter = self.registry.require(adapter_id)
        descriptor = adapter.descriptor
        denial = self.policy.denial_reason(request, descriptor)
        if denial:
            return HighAssuranceExecutionRecord.create(
                request=request,
                policy_version=self.policy.policy_version,
                status=HighAssuranceExecutionStatus.DENIED,
                denial_reason=denial,
            )
        try:
            result = adapter.execute(request, context)
        except Exception as exc:  # adapter boundary converts failures into explicit execution state
            return HighAssuranceExecutionRecord.create(
                request=request,
                policy_version=self.policy.policy_version,
                status=HighAssuranceExecutionStatus.ADAPTER_ERROR,
                denial_reason=f"adapter_exception:{type(exc).__name__}:{exc}",
            )

        if result.request_id != request.request_id:
            raise ValueError("High-assurance result is bound to a different request.")
        if result.adapter_id != descriptor.adapter_id or result.adapter_version != descriptor.version:
            raise ValueError("High-assurance result adapter identity does not match descriptor.")
        if result.evidence_state == VerificationStatus.VALIDATED:
            if self.policy.require_witness_for_validated and not result.witnesses:
                raise ValueError("Validated high-assurance results require at least one witness.")
            if (
                self.policy.require_exhaustive_envelope_for_validated
                and result.validation_envelope.completeness
                != ValidationCompleteness.EXHAUSTIVE_WITHIN_SCOPE
            ):
                raise ValueError(
                    "Validated high-assurance results require an exhaustive-within-scope envelope."
                )
        return HighAssuranceExecutionRecord.create(
            request=request,
            policy_version=self.policy.policy_version,
            status=HighAssuranceExecutionStatus.EXECUTED,
            result=result,
        )
