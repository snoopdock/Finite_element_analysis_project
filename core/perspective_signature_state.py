#!/usr/bin/env python3
"""Bounded persistence for derived scientific perspective signatures."""

from __future__ import annotations

from typing import Any, Dict, Iterable


def record_perspective_signature(state: Dict[str, Any], signature: Dict[str, Any]) -> bool:
    if not isinstance(state, dict) or not isinstance(signature, dict):
        return False
    signature_id = str(signature.get("signature_id", "")).strip()
    if not signature_id:
        return False
    graph = state.setdefault("knowledge_graph", {})
    if not isinstance(graph, dict):
        return False
    store = graph.setdefault("perspective_signatures", {})
    if not isinstance(store, dict):
        graph["perspective_signatures"] = store = {}
    current = store.get(signature_id)
    if isinstance(current, dict):
        merged = dict(current)
        merged.update(signature)
        store[signature_id] = merged
    else:
        store[signature_id] = dict(signature)
    return True


def record_perspective_signatures(
    state: Dict[str, Any],
    signatures: Iterable[Dict[str, Any]],
    *,
    max_records: int = 200,
) -> int:
    graph = state.setdefault("knowledge_graph", {})
    store = graph.setdefault("perspective_signatures", {})
    if not isinstance(store, dict):
        graph["perspective_signatures"] = store = {}
    if max_records == 0:
        store.clear()
        return 0
    count = 0
    for signature in signatures or []:
        if record_perspective_signature(state, signature):
            count += 1
    if max_records > 0 and len(store) > max_records:
        for key in sorted(store)[:-max_records]:
            store.pop(key, None)
    return count
