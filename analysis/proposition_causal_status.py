#!/usr/bin/env python3
"""Causal and inferential status for propositions; classification only."""

from __future__ import annotations

from typing import Any, Dict

CAUSAL_STATUSES = {
    "descriptive",
    "associational",
    "predictive",
    "mechanistic",
    "causal",
    "theoretical",
    "definitional",
    "unknown",
}


def normalize_causal_status(value: Any) -> str:
    normalized = str(value or "unknown").strip().lower()
    return normalized if normalized in CAUSAL_STATUSES else "unknown"


def normalize_causal_metadata(value: Any) -> Dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    result = dict(value)
    result["causal_status"] = normalize_causal_status(value.get("causal_status"))
    result["causal_mechanism"] = str(value.get("causal_mechanism") or "").strip() or None
    result["design_basis"] = str(value.get("design_basis") or "").strip() or None
    return result
