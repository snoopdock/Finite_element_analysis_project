#!/usr/bin/env python3
"""Persistence for epistemic assessments of propositions and relationships."""

from __future__ import annotations

from typing import Any, Dict, Iterable

from analysis.epistemic_state import normalize_epistemic_state


def _store(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    graph = state.setdefault("knowledge_graph", {})
    value = graph.setdefault("epistemic_states", {})
    if not isinstance(value, dict):
        graph["epistemic_states"] = {}
        value = graph["epistemic_states"]
    return value


def record_epistemic_state(
    state: Dict[str, Any],
    entity_id: str,
    assessment: Any,
    *,
    entity_type: str = "proposition",
) -> bool:
    if not isinstance(state, dict) or not str(entity_id).strip():
        return False
    normalized = normalize_epistemic_state(assessment)
    key = f"{entity_type}:{str(entity_id).strip()}"
    store = _store(state)
    current = store.get(key)
    if isinstance(current, dict):
        merged = dict(current)
        merged.update(normalized)
        merged["entity_id"] = str(entity_id).strip()
        merged["entity_type"] = str(entity_type).strip() or "proposition"
    else:
        merged = {
            "entity_id": str(entity_id).strip(),
            "entity_type": str(entity_type).strip() or "proposition",
            **normalized,
        }
    store[key] = merged
    return True


def record_epistemic_states(
    state: Dict[str, Any],
    assessments: Iterable[Dict[str, Any]],
    *,
    max_records: int = 500,
) -> int:
    if max_records == 0:
        _store(state).clear()
        return 0
    count = 0
    for item in assessments or []:
        if not isinstance(item, dict):
            continue
        entity_id = item.get("entity_id")
        if record_epistemic_state(
            state,
            entity_id,
            item,
            entity_type=item.get("entity_type", "proposition"),
        ):
            count += 1
    store = _store(state)
    if max_records > 0 and len(store) > max_records:
        for key in sorted(store)[:-max_records]:
            store.pop(key, None)
    return count
