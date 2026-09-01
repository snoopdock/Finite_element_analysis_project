#!/usr/bin/env python3
"""Temporal metadata for scientific propositions; not a truth ranking."""

from __future__ import annotations

from typing import Any, Dict

TEMPORAL_STATUSES = {
    "historical",
    "current",
    "superseded",
    "temporally_disputed",
    "unknown",
}


def normalize_temporal_status(value: Any) -> str:
    normalized = str(value or "unknown").strip().lower()
    return normalized if normalized in TEMPORAL_STATUSES else "unknown"


def normalize_temporal_metadata(value: Any) -> Dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    result = dict(value)
    result["temporal_status"] = normalize_temporal_status(value.get("temporal_status"))
    result["first_supported_at"] = str(value.get("first_supported_at") or "").strip() or None
    result["last_reviewed_at"] = str(value.get("last_reviewed_at") or "").strip() or None
    result["superseded_by"] = str(value.get("superseded_by") or "").strip() or None
    return result
