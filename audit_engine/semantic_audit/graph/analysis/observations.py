"""Structured semantic observations produced by primitive graph analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .identity import deterministic_id


@dataclass(frozen=True)
class SemanticObservation:
    """A backend-independent fact observed in the semantic graph.

    Observations remain distinct from audit findings.  An audit finding requires
    a later rule or verification step that interprets the observation.
    """

    observation_id: str
    subject_id: str
    predicate: str
    object_id: str
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    depth: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        subject_id: str,
        predicate: str,
        object_id: str,
        evidence_ids: tuple[str, ...],
        depth: int,
        metadata: dict[str, Any] | None = None,
    ) -> "SemanticObservation":
        payload = {
            "subject_id": subject_id,
            "predicate": predicate,
            "object_id": object_id,
            "evidence_ids": list(evidence_ids),
            "depth": depth,
        }
        return cls(
            observation_id=deterministic_id("obs", payload, length=24),
            subject_id=subject_id,
            predicate=predicate,
            object_id=object_id,
            evidence_ids=evidence_ids,
            depth=depth,
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "subject_id": self.subject_id,
            "predicate": self.predicate,
            "object_id": self.object_id,
            "evidence_ids": list(self.evidence_ids),
            "depth": self.depth,
            "metadata": dict(self.metadata),
        }
