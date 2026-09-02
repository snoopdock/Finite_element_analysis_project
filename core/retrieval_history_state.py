#!/usr/bin/env python3
"""State adapter for append-only retrieval acquisition history."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional


HISTORY_FIELD = "retrieval_history"
EVENTS_FIELD = "events"


def initialize_retrieval_history(state: Dict[str, Any]) -> None:
    """Ensure the retrieval history container exists without changing other state."""
    history = state.get(HISTORY_FIELD)
    if not isinstance(history, dict):
        state[HISTORY_FIELD] = {EVENTS_FIELD: []}
        return

    events = history.get(EVENTS_FIELD)
    if not isinstance(events, list):
        history[EVENTS_FIELD] = []


def get_retrieval_history(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return a defensive copy of persisted retrieval events."""
    initialize_retrieval_history(state)
    events = state[HISTORY_FIELD][EVENTS_FIELD]
    return deepcopy([event for event in events if isinstance(event, dict)])


def has_retrieval_event(state: Dict[str, Any], event_id: str) -> bool:
    """Return whether an event with the given stable ID is already persisted."""
    if not isinstance(event_id, str) or not event_id.strip():
        return False

    initialize_retrieval_history(state)
    target = event_id.strip()
    return any(
        isinstance(event, dict) and event.get("event_id") == target
        for event in state[HISTORY_FIELD][EVENTS_FIELD]
    )


def append_retrieval_event(
    state: Dict[str, Any],
    event: Dict[str, Any],
) -> bool:
    """Append one retrieval event exactly once by event_id.

    Returns True when the event was appended and False when the same event_id
    was already present.
    """
    if not isinstance(event, dict):
        raise TypeError("Retrieval event must be a dictionary.")

    event_id = event.get("event_id")
    if not isinstance(event_id, str) or not event_id.strip():
        raise ValueError("Retrieval event requires a non-empty event_id.")
    normalized_event_id = event_id.strip()

    required_fields = (
        "cycle",
        "retrieved_at",
        "report",
        "acquisition_assessment",
    )
    missing = [field for field in required_fields if field not in event]
    if missing:
        raise ValueError(
            "Retrieval event is missing required fields: "
            + ", ".join(missing)
        )

    initialize_retrieval_history(state)

    if has_retrieval_event(state, normalized_event_id):
        return False

    event_to_store = deepcopy(event)
    event_to_store["event_id"] = normalized_event_id
    state[HISTORY_FIELD][EVENTS_FIELD].append(event_to_store)
    return True


def get_retrieval_event(
    state: Dict[str, Any],
    event_id: str,
) -> Optional[Dict[str, Any]]:
    """Return one persisted event by stable event_id, if present."""
    initialize_retrieval_history(state)
    target = event_id.strip() if isinstance(event_id, str) else ""
    for event in state[HISTORY_FIELD][EVENTS_FIELD]:
        if isinstance(event, dict) and event.get("event_id") == target:
            return deepcopy(event)
    return None
