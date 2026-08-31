#!/usr/bin/env python3
"""History tracking for provenance-aware scientific propositions."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List


_TRACKED_FIELDS = (
    "statement",
    "source_ids",
    "framework",
    "assumptions",
    "conditions",
    "domain_of_validity",
    "definitions",
    "parameters",
    "boundary_conditions",
    "initial_conditions",
    "method",
    "approximation",
    "scope",
)


def _fingerprint(proposition: Dict[str, Any]) -> str:
    payload = {key: proposition.get(key) for key in _TRACKED_FIELDS}
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def record_proposition_history(state: Dict[str, Any]) -> int:
    """Record discovery/context changes for graph propositions without changing IDs."""
    graph = state.get("knowledge_graph", {})
    if not isinstance(graph, dict):
        return 0
    propositions = graph.get("propositions", {})
    if not isinstance(propositions, dict):
        return 0

    history = graph.setdefault("proposition_history", [])
    if not isinstance(history, list):
        history = []
        graph["proposition_history"] = history

    known = {}
    for event in history:
        if not isinstance(event, dict):
            continue
        proposition_id = str(event.get("proposition_id", "")).strip()
        fingerprint = str(event.get("fingerprint", "")).strip()
        if proposition_id and fingerprint:
            known[proposition_id] = fingerprint

    changed = 0
    for proposition_id, proposition in sorted(propositions.items()):
        if not isinstance(proposition, dict):
            continue
        proposition_id = str(proposition_id)
        fingerprint = _fingerprint(proposition)
        previous = known.get(proposition_id)
        if previous == fingerprint:
            continue

        event = {
            "proposition_id": proposition_id,
            "event": "discovered" if previous is None else "updated",
            "fingerprint": fingerprint,
            "source_ids": sorted({str(v) for v in proposition.get("source_ids", []) if v}),
            "framework": str(proposition.get("framework", "")).strip(),
        }
        history.append(event)
        known[proposition_id] = fingerprint
        changed += 1

    return changed
