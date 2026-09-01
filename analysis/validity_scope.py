#!/usr/bin/env python3
"""Structured validity-scope model for scientific propositions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

VALIDITY_TYPES = {
    "universal",
    "conditional",
    "approximate",
    "empirical",
    "heuristic",
    "definitional",
    "unknown",
}


@dataclass(frozen=True)
class ValidityScope:
    """Describe where and under what conditions a proposition is claimed to hold."""

    validity_id: str
    proposition_id: str
    type: str = "unknown"
    framework: Optional[str] = None
    domain_of_validity: Optional[str] = None
    regime: Optional[str] = None
    conditions: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    exceptions: List[str] = field(default_factory=list)
    approximation: Optional[str] = None
    evidence_relation_ids: List[str] = field(default_factory=list)
    status: str = "proposed"

    def __post_init__(self) -> None:
        object.__setattr__(self, "validity_id", str(self.validity_id).strip())
        object.__setattr__(self, "proposition_id", str(self.proposition_id).strip())
        normalized_type = str(self.type or "unknown").strip().lower()
        if normalized_type not in VALIDITY_TYPES:
            normalized_type = "unknown"
        object.__setattr__(self, "type", normalized_type)
        if not self.validity_id or not self.proposition_id:
            raise ValueError("validity_id and proposition_id are required")
        for field_name in (
            "conditions",
            "assumptions",
            "limitations",
            "exceptions",
            "evidence_relation_ids",
        ):
            values = getattr(self, field_name)
            cleaned = []
            seen = set()
            for value in values or []:
                text = str(value).strip()
                if text and text not in seen:
                    seen.add(text)
                    cleaned.append(text)
            object.__setattr__(self, field_name, cleaned)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "validity_id": self.validity_id,
            "proposition_id": self.proposition_id,
            "type": self.type,
            "framework": self.framework,
            "domain_of_validity": self.domain_of_validity,
            "regime": self.regime,
            "conditions": list(self.conditions),
            "assumptions": list(self.assumptions),
            "limitations": list(self.limitations),
            "exceptions": list(self.exceptions),
            "approximation": self.approximation,
            "evidence_relation_ids": list(self.evidence_relation_ids),
            "status": self.status,
        }


def normalize_validity_scope(value: Any) -> Optional[Dict[str, Any]]:
    """Normalize a validity-scope mapping without inventing missing facts."""
    if isinstance(value, ValidityScope):
        return value.to_dict()
    if not isinstance(value, dict):
        return None

    try:
        scope = ValidityScope(
            validity_id=value.get("validity_id", ""),
            proposition_id=value.get("proposition_id", ""),
            type=value.get("type", "unknown"),
            framework=value.get("framework"),
            domain_of_validity=value.get("domain_of_validity"),
            regime=value.get("regime"),
            conditions=value.get("conditions", []),
            assumptions=value.get("assumptions", []),
            limitations=value.get("limitations", []),
            exceptions=value.get("exceptions", []),
            approximation=value.get("approximation"),
            evidence_relation_ids=value.get("evidence_relation_ids", []),
            status=value.get("status", "proposed"),
        )
    except (TypeError, ValueError):
        return None
    return scope.to_dict()
