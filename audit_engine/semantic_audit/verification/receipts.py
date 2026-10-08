
"""Immutable verification receipts."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from audit_engine.semantic_audit.graph.analysis.identity import deterministic_id
from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus

from .models import VerificationAttempt, VerificationDecision, VerificationObligation


VERIFICATION_RECEIPT_SCHEMA_VERSION = "semantic_verification_receipt/v1"


@dataclass(frozen=True)
class VerificationReceipt:
    receipt_id: str
    attempt_id: str
    obligation_id: str
    source_analysis_id: str
    verifier_id: str
    verifier_version: str
    decision: VerificationDecision
    evidence_state: VerificationStatus
    evidence_ids: tuple[str, ...]
    graph_fingerprint: str
    semantic_context_fingerprint: str
    details: Mapping[str, Any] = field(default_factory=dict)
    error: str | None = None
    schema_version: str = VERIFICATION_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))

    @classmethod
    def seal(
        cls,
        obligation: VerificationObligation,
        attempt: VerificationAttempt,
    ) -> "VerificationReceipt":
        if attempt.obligation_id != obligation.obligation_id:
            raise ValueError("Verification attempt is bound to a different obligation.")
        if not set(attempt.evidence_ids).issubset(set(obligation.evidence_ids)):
            raise ValueError("Verification attempt references evidence outside its obligation.")
        payload = {
            "attempt_id": attempt.attempt_id,
            "obligation_id": obligation.obligation_id,
            "source_analysis_id": obligation.source_analysis_id,
            "verifier_id": attempt.verifier_id,
            "verifier_version": attempt.verifier_version,
            "decision": attempt.decision.value,
            "evidence_state": attempt.evidence_state.value,
            "evidence_ids": list(attempt.evidence_ids),
            "graph_fingerprint": obligation.graph_fingerprint,
            "semantic_context_fingerprint": obligation.semantic_context_fingerprint,
            "details": dict(attempt.details),
            "error": attempt.error,
        }
        return cls(
            receipt_id=deterministic_id("verification-receipt", payload, length=24),
            attempt_id=attempt.attempt_id,
            obligation_id=obligation.obligation_id,
            source_analysis_id=obligation.source_analysis_id,
            verifier_id=attempt.verifier_id,
            verifier_version=attempt.verifier_version,
            decision=attempt.decision,
            evidence_state=attempt.evidence_state,
            evidence_ids=attempt.evidence_ids,
            graph_fingerprint=obligation.graph_fingerprint,
            semantic_context_fingerprint=obligation.semantic_context_fingerprint,
            details=dict(attempt.details),
            error=attempt.error,
        )

    def is_stale_for(
        self,
        *,
        graph_fingerprint: str,
        semantic_context_fingerprint: str,
    ) -> bool:
        return (
            self.graph_fingerprint != graph_fingerprint
            or self.semantic_context_fingerprint != semantic_context_fingerprint
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "attempt_id": self.attempt_id,
            "obligation_id": self.obligation_id,
            "source_analysis_id": self.source_analysis_id,
            "verifier_id": self.verifier_id,
            "verifier_version": self.verifier_version,
            "decision": self.decision.value,
            "evidence_state": self.evidence_state.value,
            "evidence_ids": list(self.evidence_ids),
            "graph_fingerprint": self.graph_fingerprint,
            "semantic_context_fingerprint": self.semantic_context_fingerprint,
            "details": dict(self.details),
            "error": self.error,
        }
