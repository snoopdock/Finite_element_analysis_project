#!/usr/bin/env python3
"""Persist explicit proposition lifecycle events alongside existing history."""

from __future__ import annotations

import hashlib
from typing import Any, Dict

from analysis.proposition_lifecycle import normalize_lifecycle_event


def lifecycle_event_id(
    proposition_id: str,
    change_type: str,
    previous_statement: str = "",
    new_statement: str = "",
) -> str:
    payload = "|".join([
        str(proposition_id).strip(),
        str(change_type).strip().lower(),
        str(previous_statement).strip(),
        str(new_statement).strip(),
    ])
    return "life-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def record_lifecycle_event(state: Dict[str, Any], event: Dict[str, Any]) -> bool:
    normalized = normalize_lifecycle_event(event)
    if normalized is None:
        return False
    normalized["event_id"] = lifecycle_event_id(
        normalized["proposition_id"],
        normalized["change_type"],
        normalized.get("previous_statement", ""),
        normalized.get("new_statement", ""),
    )
    graph = state.setdefault("knowledge_graph", {})
    history = graph.setdefault("proposition_lifecycle", [])
    if not isinstance(history, list):
        graph["proposition_lifecycle"] = history = []
    if any(isinstance(item, dict) and item.get("event_id") == normalized["event_id"] for item in history):
        return False
    history.append(normalized)
    return True
