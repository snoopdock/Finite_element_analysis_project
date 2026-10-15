
"""G3.1 verification orchestration."""

from __future__ import annotations

from .models import VerificationContext, VerificationObligation
from .receipts import VerificationReceipt
from .registry import VerifierRegistry


class VerificationService:
    """Execute an explicit obligation using a registered verifier."""

    def __init__(self, registry: VerifierRegistry) -> None:
        self.registry = registry

    def verify(
        self,
        obligation: VerificationObligation,
        analysis_result,
        *,
        verifier_id: str | None = None,
        semantic_graph=None,
    ) -> VerificationReceipt:
        context = VerificationContext(
            analysis_result=analysis_result,
            semantic_graph=semantic_graph,
        )
        context.validate_obligation_binding(obligation)

        if verifier_id is None:
            verifier = self.registry.resolve(obligation)
        else:
            verifier = self.registry.get(verifier_id)
            if verifier is None:
                raise LookupError(f"Unknown verifier: {verifier_id!r}")
            if (
                obligation.requested_verifier_ids
                and verifier.descriptor.verifier_id not in obligation.requested_verifier_ids
            ):
                raise ValueError("Selected verifier is not permitted by the obligation.")
            if obligation.obligation_type not in verifier.descriptor.supported_obligation_types:
                raise ValueError(
                    f"Verifier {verifier_id!r} does not support obligation type "
                    f"{obligation.obligation_type!r}."
                )

        if (
            obligation.requested_verifier_ids
            and verifier.descriptor.verifier_id not in obligation.requested_verifier_ids
        ):
            raise ValueError("Selected verifier is not permitted by the obligation.")

        attempt = verifier.verify(obligation, context)
        from .integrity import validate_attempt_identity, validate_receipt_identity
        validate_attempt_identity(attempt, obligation, verifier.descriptor)
        if semantic_graph is not None:
            from audit_engine.semantic_audit.graph.analysis.identity import graph_fingerprint
            if graph_fingerprint(semantic_graph) != obligation.graph_fingerprint:
                raise ValueError('Source graph changed during registered verifier execution')
        receipt = VerificationReceipt.seal(obligation, attempt)
        validate_receipt_identity(receipt, obligation)
        return receipt
