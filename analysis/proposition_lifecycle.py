#!/usr/bin/env python3
"""Scientific lifecycle semantics for proposition changes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

CHANGE_TYPES = {
    "clarification",
    "restriction",
    "generalization",
    "correction",
    "replacement",
    "contradiction",
}


@dataclass(frozen=True)
class PropositionLifecycleEvent:
    event_id: str
    proposition_id: str
    change_type: str
    previous_statement: str = ""
    new_statement: str = ""
    reason: str = ""
    related_proposition_ids: List[str] = field(default_factory=list)
    source_ids: List[str] = field(default_factory=list)
    status: str = "proposed"

    def __post_init__(self) -> None:
        event_id = str(self.event_id).strip()
        proposition_id = str(self.proposition_id).strip()
        change_type = str(self.change_type or "").strip().lower()
        if not event_id or not proposition_id:
            raise ValueError("event_id and proposition_id are required")
        if change_type not in CHANGE_TYPES:
            raise ValueError(f"unsupported proposition change type: {change_type}")
        object.__setattr__(self, "event_id", event_id)
        object.__setattr__(self, "proposition_id", proposition_id)
        object.__setattr__(self, "change_type", change_type)
        object.__setattr__(self, "previous_statement", str(self.previous_statement or "").strip())
        object.__setattr__(self, "new_statement", str(self.new_statement or "").strip())
        object.__setattr__(self, "reason", str(self.reason or "").strip())
        for name in ("related_proposition_ids", "source_ids"):
            values = []
            seen = set()
            for value in getattr(self, name) or []:
                text = str(value).strip()
                if text and text not in seen:
                    seen.add(text)
                    values.append(text)
            object.__setattr__(self, name, values)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "proposition_id": self.proposition_id,
            "change_type": self.change_type,
            "previous_statement": self.previous_statement,
            "new_statement": self.new_statement,
            "reason": self.reason,
            "related_proposition_ids": list(self.related_proposition_ids),
            "source_ids": list(self.source_ids),
            "status": self.status,
        }


def normalize_lifecycle_event(value: Any) -> Dict[str, Any] | None:
    if isinstance(value, PropositionLifecycleEvent):
        return value.to_dict()
    if not isinstance(value, dict):
        return None
    try:
        return PropositionLifecycleEvent(**value).to_dict()
    except (TypeError, ValueError):
        return None
