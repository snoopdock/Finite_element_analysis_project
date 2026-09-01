#!/usr/bin/env python3
"""Evidence-backed support records for scientific graph relationships."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class RelationshipSupport:
    support_id: str
    relationship_id: str
    proposition_ids: List[str] = field(default_factory=list)
    source_ids: List[str] = field(default_factory=list)
    evidence_relation_ids: List[str] = field(default_factory=list)
    validity_ids: List[str] = field(default_factory=list)
    mechanism: str | None = None
    conditions: List[str] = field(default_factory=list)
    rationale: str = ""
    status: str = "proposed"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "support_id": self.support_id,
            "relationship_id": self.relationship_id,
            "proposition_ids": list(self.proposition_ids),
            "source_ids": list(self.source_ids),
            "evidence_relation_ids": list(self.evidence_relation_ids),
            "validity_ids": list(self.validity_ids),
            "mechanism": self.mechanism,
            "conditions": list(self.conditions),
            "rationale": self.rationale,
            "status": self.status,
        }


def support_id_from_payload(relationship_id: str, payload: Dict[str, Any]) -> str:
    encoded = json.dumps(
        {"relationship_id": relationship_id, **payload},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return "relsup-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def normalize_relationship_support(value: Any) -> Dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    relationship_id = str(value.get("relationship_id", "")).strip()
    if not relationship_id:
        return None

    def clean(values: Any) -> List[str]:
        result: List[str] = []
        seen = set()
        for item in values or []:
            text = str(item).strip()
            if text and text not in seen:
                seen.add(text)
                result.append(text)
        return sorted(result)

    payload = {
        "proposition_ids": clean(value.get("proposition_ids")),
        "source_ids": clean(value.get("source_ids")),
        "evidence_relation_ids": clean(value.get("evidence_relation_ids")),
        "validity_ids": clean(value.get("validity_ids")),
        "mechanism": str(value.get("mechanism") or "").strip() or None,
        "conditions": clean(value.get("conditions")),
        "rationale": str(value.get("rationale") or "").strip(),
        "status": str(value.get("status") or "proposed").strip().lower(),
    }
    return RelationshipSupport(
        support_id=str(value.get("support_id") or support_id_from_payload(relationship_id, payload)).strip(),
        relationship_id=relationship_id,
        **payload,
    ).to_dict()
