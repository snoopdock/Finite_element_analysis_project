"""Evidence records derived from canonical semantic graph observations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge

from .identity import edge_fingerprint
from .models import VerificationStatus


@dataclass(frozen=True)
class EvidenceRecord:
    """Traceable evidence for one graph observation.

    Presence of a semantic edge is recorded as ``OBSERVED`` evidence.  The
    record deliberately does not promote graph presence to semantic validity.
    """

    evidence_id: str
    subject_id: str
    predicate: str
    object_id: str
    verification_status: VerificationStatus = VerificationStatus.OBSERVED
    source_kind: str = "semantic_edge"
    provenance: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_edge(cls, edge: SemanticEdge) -> "EvidenceRecord":
        return cls(
            evidence_id=edge_fingerprint(edge),
            subject_id=edge.source_id,
            predicate=edge.relation_type,
            object_id=edge.target_id,
            provenance={
                "edge_attributes": dict(edge.attributes),
                "edge_metadata": dict(edge.metadata),
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "subject_id": self.subject_id,
            "predicate": self.predicate,
            "object_id": self.object_id,
            "verification_status": self.verification_status.value,
            "source_kind": self.source_kind,
            "provenance": dict(self.provenance),
        }
