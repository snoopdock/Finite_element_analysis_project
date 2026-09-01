#!/usr/bin/env python3
"""Bounded persistence for proposed and assessed validity scopes."""

from __future__ import annotations

from typing import Any, Dict, Iterable

from analysis.validity_scope import normalize_validity_scope


def _scopes(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    graph = state.setdefault("knowledge_graph", {})
    if not isinstance(graph, dict):
        return {}
    value = graph.setdefault("validity_scopes", {})
    if not isinstance(value, dict):
        graph["validity_scopes"] = {}
        value = graph["validity_scopes"]
    return value


def record_validity_scope(state: Dict[str, Any], scope: Any) -> bool:
    """Persist one normalized validity scope without changing proposition identity."""
    normalized = normalize_validity_scope(scope)
    if normalized is None:
        return False
    scopes = _scopes(state)
    existing = scopes.get(normalized["validity_id"], {})
    if isinstance(existing, dict):
        previous_status = str(existing.get("status", "proposed")).strip().lower()
        new_status = str(normalized.get("status", "proposed")).strip().lower()
        if previous_status in {"assessed", "superseded"} and new_status == "proposed":
            normalized["status"] = previous_status
        merged = {**existing, **normalized}
    else:
        merged = normalized
    scopes[normalized["validity_id"]] = merged
    return True


def record_validity_scopes(
    state: Dict[str, Any],
    scopes: Iterable[Any],
    *,
    max_records: int = 200,
) -> int:
    """Persist validity scopes with a deterministic record bound."""
    if max_records == 0:
        _scopes(state).clear()
        return 0
    count = 0
    for scope in scopes or []:
        if record_validity_scope(state, scope):
            count += 1
    records = _scopes(state)
    if max_records > 0 and len(records) > max_records:
        for key in sorted(records)[:-max_records]:
            records.pop(key, None)
    return count
