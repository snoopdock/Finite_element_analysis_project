#!/usr/bin/env python3
"""Bounded adapter for persisting scientific perspective comparisons."""

from __future__ import annotations

from typing import Any, Dict, List

from core.perspective_state import normalize_comparison_record, upsert_comparison


def record_comparison(
    state: Dict[str, Any],
    comparison: Dict[str, Any],
    *,
    max_records: int = 200,
) -> Dict[str, Any]:
    """Persist a comparison only when it has a valid, non-skipped result."""
    if not isinstance(comparison, dict) or comparison.get("skipped"):
        return state

    normalized = normalize_comparison_record(comparison)
    if not normalized.get("comparison_id"):
        return state

    history = state.get("perspective_comparisons", [])
    if not isinstance(history, list):
        history = []

    state["perspective_comparisons"] = upsert_comparison(
        history,
        normalized,
        max_records=max_records,
    )
    return state


def record_comparisons(
    state: Dict[str, Any],
    comparisons: List[Dict[str, Any]],
    *,
    max_records: int = 200,
) -> Dict[str, Any]:
    """Persist multiple comparison records with bounded history."""
    for comparison in comparisons or []:
        record_comparison(state, comparison, max_records=max_records)
    return state
