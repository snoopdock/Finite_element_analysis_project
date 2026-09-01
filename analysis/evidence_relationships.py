#!/usr/bin/env python3
"""Explicit, provenance-aware relationships between evidence and propositions."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Iterable, List, Optional

_ALLOWED = {
    "supports",
    "challenges",
    "qualifies",
    "provides_context_for",
    "reproduces",
    "does_not_address",
    "unknown",
}


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _clean_ids(values: Iterable[Any]) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values or []:
        text = _clean(value)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def evidence_relation_id(source_id: str, proposition_id: str) -> str:
    """Return a stable identity for a source/proposition evidence relation."""
    payload = "|".join((_clean(source_id), _clean(proposition_id)))
    return "er-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def normalize_evidence_relation(value: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalize an evidence-to-proposition relation without asserting verification."""
    raw = value if isinstance(value, dict) else {}
    relation = _clean(raw.get("relationship", "unknown")).lower()
    if relation not in _ALLOWED:
        relation = "unknown"
    try:
        confidence = max(0.0, min(1.0, float(raw.get("classification_confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "relationship": relation,
        "classification_confidence": round(confidence, 4),
        "passage_ids": _clean_ids(raw.get("passage_ids", [])),
        "reason": _clean(raw.get("reason", "")),
    }


def make_evidence_relation(
    source_id: str,
    proposition_id: str,
    analysis: Optional[Dict[str, Any]],
    *,
    provenance: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a traceable relation; this does not mark the proposition as verified."""
    source_id = _clean(source_id)
    proposition_id = _clean(proposition_id)
    normalized = normalize_evidence_relation(analysis)
    record = {
        "evidence_relation_id": evidence_relation_id(source_id, proposition_id),
        "source_id": source_id,
        "proposition_id": proposition_id,
        **normalized,
        "status": "assessed",
    }
    if isinstance(provenance, dict):
        record["provenance"] = {
            "created_by": _clean(provenance.get("created_by", "")),
            "created_at": _clean(provenance.get("created_at", "")),
            "method": _clean(provenance.get("method", "")),
        }
    return record
