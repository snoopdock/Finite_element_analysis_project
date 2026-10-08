
"""Evidence corroboration verifier."""

from __future__ import annotations

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus

from .models import (
    VerificationAttempt,
    VerificationContext,
    VerificationDecision,
    VerificationObligation,
)
from .verifier import VerifierDescriptor


class EvidenceCorroborationVerifier:
    """Confirm that evidence spans explicitly independent source groups.

    Independence is never inferred from multiple edge IDs. Evidence must expose
    an explicit provenance key (directly or in ``edge_metadata``); otherwise the
    verifier returns ``INCONCLUSIVE`` rather than overstating corroboration.
    """

    descriptor = VerifierDescriptor(
        verifier_id="evidence-corroboration",
        version="1.0.0",
        supported_obligation_types=("evidence_corroboration",),
    )

    @staticmethod
    def _independence_value(record, key: str):
        value = record.provenance.get(key)
        if value is not None:
            return value
        edge_metadata = record.provenance.get("edge_metadata")
        if isinstance(edge_metadata, dict):
            return edge_metadata.get(key)
        return None

    def verify(self, obligation, context):
        context.validate_obligation_binding(obligation)
        evidence = context.selected_evidence(obligation)
        minimum = int(obligation.parameters.get("minimum_independent_sources", 2))
        if minimum < 2:
            raise ValueError("minimum_independent_sources must be at least 2.")
        key = str(obligation.parameters.get("independence_key", "source_id")).strip()
        if not key:
            raise ValueError("independence_key must be non-empty.")

        groups = []
        missing = []
        for record in evidence:
            value = self._independence_value(record, key)
            if value is None or str(value).strip() == "":
                missing.append(record.evidence_id)
            else:
                groups.append(str(value))
        unique_groups = tuple(sorted(set(groups)))

        if len(unique_groups) >= minimum:
            decision = VerificationDecision.CONFIRMED
            state = VerificationStatus.CORROBORATED
        else:
            decision = VerificationDecision.INCONCLUSIVE
            state = VerificationStatus.INCONCLUSIVE

        return VerificationAttempt.create(
            obligation_id=obligation.obligation_id,
            verifier_id=self.descriptor.verifier_id,
            verifier_version=self.descriptor.version,
            decision=decision,
            evidence_state=state,
            evidence_ids=[record.evidence_id for record in evidence],
            details={
                "independence_key": key,
                "minimum_independent_sources": minimum,
                "independent_source_groups": list(unique_groups),
                "evidence_missing_independence_key": sorted(missing),
            },
        )
