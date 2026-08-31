#!/usr/bin/env python3
"""Persistent helpers for auditable writer/OAA decisions."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List


DEFAULT_MAX_DECISIONS = 100


def decision_fingerprint(record: Dict[str, Any]) -> str:
    """Return a stable digest for one decision record."""
    payload = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_decision(record: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize one decision record without changing its scientific meaning."""
    if not isinstance(record, dict):
        raise TypeError("Decision record must be a dictionary.")

    normalized = {
        "section_id": record.get("section_id"),
        "title": str(record.get("title", "")).strip(),
        "eta": _bounded_float(record.get("eta", 0.0)),
        "priority": _nonnegative_float(record.get("priority", 0.0)),
        "selected": bool(record.get("selected", False)),
        "model_index": int(record.get("model_index", 0)),
        "model": str(record.get("model", "")),
    }
    normalized["fingerprint"] = decision_fingerprint(normalized)
    return normalized


def append_decision_history(
    state: Dict[str, Any],
    records: Iterable[Dict[str, Any]],
    *,
    max_records: int = DEFAULT_MAX_DECISIONS,
) -> List[Dict[str, Any]]:
    """Append normalized decision records and keep a bounded history."""
    history = state.get("decision_history", [])
    if not isinstance(history, list):
        history = []

    for record in records or []:
        normalized = normalize_decision(record)
        history.append(normalized)

    limit = max(0, int(max_records))
    if limit == 0:
        history = []
    elif len(history) > limit:
        history = history[-limit:]

    state["decision_history"] = history
    return history


def _bounded_float(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _nonnegative_float(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0
