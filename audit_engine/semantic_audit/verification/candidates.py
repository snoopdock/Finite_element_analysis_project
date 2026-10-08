
"""Candidate knowledge artifacts isolated from canonical semantic knowledge."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from audit_engine.semantic_audit.graph.analysis.identity import deterministic_id
from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus


@dataclass(frozen=True)
class CandidateKnowledge:
    """A proposed semantic relation that has no canonical authority."""

    candidate_id: str
    subject_id: str
    predicate: str
    object_id: str
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    state: VerificationStatus = VerificationStatus.PROPOSED
    provenance: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        subject_id: str,
        predicate: str,
        object_id: str,
        evidence_ids: Sequence[str] = (),
        provenance: Mapping[str, Any] | None = None,
    ) -> "CandidateKnowledge":
        values = [str(subject_id).strip(), str(predicate).strip(), str(object_id).strip()]
        if not all(values):
            raise ValueError("Candidate knowledge subject, predicate, and object must be non-empty.")
        payload = {
            "subject_id": values[0],
            "predicate": values[1],
            "object_id": values[2],
            "evidence_ids": sorted(set(evidence_ids)),
            "provenance": dict(provenance or {}),
        }
        return cls(
            candidate_id=deterministic_id("candidate", payload, length=24),
            subject_id=values[0],
            predicate=values[1],
            object_id=values[2],
            evidence_ids=tuple(dict.fromkeys(evidence_ids)),
            provenance=dict(provenance or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "subject_id": self.subject_id,
            "predicate": self.predicate,
            "object_id": self.object_id,
            "evidence_ids": list(self.evidence_ids),
            "state": self.state.value,
            "provenance": dict(self.provenance),
        }
