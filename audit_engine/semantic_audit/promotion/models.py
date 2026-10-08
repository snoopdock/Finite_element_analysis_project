"""Candidate-to-canonical promotion contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus


@dataclass(frozen=True)
class CandidatePromotionPolicy:
    policy_id: str
    version: str
    canonical_predicate: str | None = None
    minimum_evidence_state: VerificationStatus = VerificationStatus.VALIDATED
    allowed_verifier_ids: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.policy_id.strip() or not self.version.strip():
            raise ValueError("Promotion policy id and version must be non-empty.")
        if self.canonical_predicate is not None and not self.canonical_predicate.strip():
            raise ValueError("canonical_predicate must be None or non-empty.")


@dataclass(frozen=True)
class CandidatePromotionResult:
    candidate_id: str
    promoted: bool
    reason: str
    relationship_fingerprint: str | None = None
    canonical_predicate: str | None = None
    graph_fingerprint_before: str | None = None
    graph_fingerprint_after: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "promoted": self.promoted,
            "reason": self.reason,
            "relationship_fingerprint": self.relationship_fingerprint,
            "canonical_predicate": self.canonical_predicate,
            "graph_fingerprint_before": self.graph_fingerprint_before,
            "graph_fingerprint_after": self.graph_fingerprint_after,
            "metadata": dict(self.metadata),
        }
