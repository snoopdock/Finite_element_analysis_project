#!/usr/bin/env python3
"""Provenance records connecting a source to its role regarding a proposition."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

ASSERTION_ROLES = {
    "proposes",
    "supports",
    "challenges",
    "qualifies",
    "reproduces",
    "extends",
    "uses",
    "reviews",
    "cites",
}


@dataclass(frozen=True)
class AssertionRecord:
    """Record how one source relates to one proposition."""

    assertion_id: str
    proposition_id: str
    source_id: str
    role: str
    evidence_relation_ids: List[str] = field(default_factory=list)
    validity_id: str | None = None
    passage_ids: List[str] = field(default_factory=list)
    status: str = "proposed"
    provenance: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "assertion_id", str(self.assertion_id).strip())
        object.__setattr__(self, "proposition_id", str(self.proposition_id).strip())
        object.__setattr__(self, "source_id", str(self.source_id).strip())
        role = str(self.role or "").strip().lower()
        if role not in ASSERTION_ROLES:
            raise ValueError(f"unsupported assertion role: {role}")
        object.__setattr__(self, "role", role)
        for field_name in ("evidence_relation_ids", "passage_ids"):
            values = getattr(self, field_name)
            cleaned = []
            seen = set()
            for value in values or []:
                text = str(value).strip()
                if text and text not in seen:
                    seen.add(text)
                    cleaned.append(text)
            object.__setattr__(self, field_name, cleaned)
        if not self.assertion_id or not self.proposition_id or not self.source_id:
            raise ValueError("assertion_id, proposition_id and source_id are required")
        if self.status in {"verified", "accepted", "scientifically_confirmed"}:
            raise ValueError("assertion provenance cannot itself establish scientific verification")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assertion_id": self.assertion_id,
            "proposition_id": self.proposition_id,
            "source_id": self.source_id,
            "role": self.role,
            "evidence_relation_ids": list(self.evidence_relation_ids),
            "validity_id": self.validity_id,
            "passage_ids": list(self.passage_ids),
            "status": self.status,
            "provenance": dict(self.provenance),
        }


def normalize_assertion(value: Any) -> Dict[str, Any] | None:
    if isinstance(value, AssertionRecord):
        return value.to_dict()
    if not isinstance(value, dict):
        return None
    try:
        return AssertionRecord(**value).to_dict()
    except (TypeError, ValueError):
        return None
