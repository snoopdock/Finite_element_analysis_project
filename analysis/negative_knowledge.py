#!/usr/bin/env python3
"""Typed records for unresolved, rejected, disproven, or superseded knowledge."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, List

NEGATIVE_STATUSES = {
    "unresolved",
    "rejected_for_insufficient_evidence",
    "contradicted_under_conditions",
    "disproven",
    "superseded",
}


@dataclass(frozen=True)
class NegativeKnowledgeRecord:
    record_id: str
    entity_id: str
    entity_type: str
    status: str
    reason: str
    evidence_relation_ids: List[str]
    provenance_trace_ids: List[str]
    future_recheck: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "status": self.status,
            "reason": self.reason,
            "evidence_relation_ids": list(self.evidence_relation_ids),
            "provenance_trace_ids": list(self.provenance_trace_ids),
            "future_recheck": bool(self.future_recheck),
        }


def _identity(entity_id: str, entity_type: str, status: str, reason: str) -> str:
    payload = json.dumps({
        "entity_id": str(entity_id).strip(),
        "entity_type": str(entity_type).strip(),
        "status": str(status).strip().lower(),
        "reason": str(reason).strip(),
    }, sort_keys=True)
    return "neg-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def normalize_negative_knowledge(value: Any) -> Dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    entity_id = str(value.get("entity_id", "")).strip()
    entity_type = str(value.get("entity_type", "")).strip()
    status = str(value.get("status", "")).strip().lower()
    reason = str(value.get("reason", "")).strip()
    if not entity_id or not entity_type or status not in NEGATIVE_STATUSES or not reason:
        return None

    def clean(values: Any) -> List[str]:
        result = []
        seen = set()
        for item in values or []:
            text = str(item).strip()
            if text and text not in seen:
                seen.add(text)
                result.append(text)
        return sorted(result)

    record = NegativeKnowledgeRecord(
        record_id=str(value.get("record_id") or _identity(entity_id, entity_type, status, reason)).strip(),
        entity_id=entity_id,
        entity_type=entity_type,
        status=status,
        reason=reason,
        evidence_relation_ids=clean(value.get("evidence_relation_ids")),
        provenance_trace_ids=clean(value.get("provenance_trace_ids")),
        future_recheck=bool(value.get("future_recheck", False)),
    )
    return record.to_dict()
