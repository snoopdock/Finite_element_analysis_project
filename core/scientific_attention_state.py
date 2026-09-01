#!/usr/bin/env python3
"""Persistence for scientific-attention signals keyed by section or proposition."""

from __future__ import annotations

from typing import Any, Dict

from analysis.scientific_attention import normalize_attention, attention_priority


def record_scientific_attention(
    state: Dict[str, Any],
    entity_id: str,
    signals: Any,
    *,
    entity_type: str = "section",
) -> bool:
    if not isinstance(state, dict) or not str(entity_id).strip():
        return False
    normalized = normalize_attention(signals)
    graph = state.setdefault("knowledge_graph", {})
    if not isinstance(graph, dict):
        return False
    store = graph.setdefault("scientific_attention", {})
    if not isinstance(store, dict):
        graph["scientific_attention"] = store = {}
    key = f"{entity_type}:{str(entity_id).strip()}"
    store[key] = {
        "entity_id": str(entity_id).strip(),
        "entity_type": str(entity_type).strip() or "section",
        "signals": normalized,
        "priority_hint": attention_priority(normalized),
    }
    return True
