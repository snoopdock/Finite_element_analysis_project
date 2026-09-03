#!/usr/bin/env python3
"""State adapter for append-only retrieval-attention lifecycle persistence."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional


HISTORY_FIELD = "retrieval_attention_lifecycle_history"
EVENTS_FIELD = "events"
REQUIRED_FIELDS = (
    "lifecycle_event_id",
    "attention_id",
    "previous_status",
    "new_status",
    "transition_reason",
    "created_at",
    "actor",
    "schema_version",
)


class LifecyclePersistenceError(Exception):
    """Base error for lifecycle persistence failures."""


class LifecycleEventIntegrityError(LifecyclePersistenceError):
    """Raised when an existing lifecycle_event_id has conflicting content."""


class LifecycleEventValidationError(LifecyclePersistenceError, ValueError):
    """Raised when a lifecycle event does not satisfy its persistence contract."""


def initialize_lifecycle_history(state: Dict[str, Any]) -> None:
    """Ensure the lifecycle-history container exists without touching other state."""
    if not isinstance(state, dict):
        raise TypeError("state must be a dictionary.")

    history = state.get(HISTORY_FIELD)
    if not isinstance(history, dict):
        state[HISTORY_FIELD] = {EVENTS_FIELD: []}
        return

    events = history.get(EVENTS_FIELD)
    if not isinstance(events, list):
        history[EVENTS_FIELD] = []


def _canonical_event(event: Dict[str, Any]) -> Dict[str, Any]:
    return {field: deepcopy(event[field]) for field in REQUIRED_FIELDS}


def _validate_event(event: Dict[str, Any]) -> str:
    if not isinstance(event, dict):
        raise LifecycleEventValidationError("Lifecycle event must be a dictionary.")

    missing = [field for field in REQUIRED_FIELDS if field not in event]
    if missing:
        raise LifecycleEventValidationError(
            "Lifecycle event is missing required fields: " + ", ".join(missing)
        )

    lifecycle_event_id = event.get("lifecycle_event_id")
    attention_id = event.get("attention_id")
    previous_status = event.get("previous_status")
    new_status = event.get("new_status")
    transition_reason = event.get("transition_reason")
    created_at = event.get("created_at")
    actor = event.get("actor")
    schema_version = event.get("schema_version")

    if not isinstance(lifecycle_event_id, str) or not lifecycle_event_id.strip():
        raise LifecycleEventValidationError("lifecycle_event_id must be a non-empty string.")
    if not isinstance(attention_id, str) or not attention_id.strip():
        raise LifecycleEventValidationError("attention_id must be a non-empty string.")
    if previous_status is not None and previous_status not in {"open", "addressed", "closed"}:
        raise LifecycleEventValidationError("previous_status is not a valid lifecycle state.")
    if new_status not in {"open", "addressed", "closed"}:
        raise LifecycleEventValidationError("new_status is not a valid lifecycle state.")
    if previous_status is None:
        if new_status != "open":
            raise LifecycleEventValidationError("Only null-to-open is valid for initial creation.")
    elif (previous_status, new_status) not in {
        ("open", "addressed"),
        ("open", "closed"),
        ("addressed", "closed"),
    }:
        raise LifecycleEventValidationError(
            f"Invalid lifecycle transition: {previous_status!r} -> {new_status!r}."
        )
    if not isinstance(transition_reason, str) or not transition_reason.strip():
        raise LifecycleEventValidationError("transition_reason must be a non-empty string.")
    if not isinstance(created_at, str) or not created_at.strip():
        raise LifecycleEventValidationError("created_at must be a non-empty string.")
    if not isinstance(actor, str) or not actor.strip():
        raise LifecycleEventValidationError("actor must be a non-empty string.")
    if schema_version != 1:
        raise LifecycleEventValidationError("Unsupported lifecycle event schema_version.")

    return lifecycle_event_id.strip()


def get_lifecycle_history(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return defensive copies of all persisted lifecycle events."""
    initialize_lifecycle_history(state)
    return deepcopy(
        [
            event
            for event in state[HISTORY_FIELD][EVENTS_FIELD]
            if isinstance(event, dict)
        ]
    )


def has_lifecycle_event(state: Dict[str, Any], lifecycle_event_id: str) -> bool:
    """Return whether a lifecycle event with the given stable ID exists."""
    if not isinstance(lifecycle_event_id, str) or not lifecycle_event_id.strip():
        return False

    initialize_lifecycle_history(state)
    target = lifecycle_event_id.strip()
    return any(
        isinstance(event, dict) and event.get("lifecycle_event_id") == target
        for event in state[HISTORY_FIELD][EVENTS_FIELD]
    )


def append_lifecycle_event(state: Dict[str, Any], event: Dict[str, Any]) -> bool:
    """Persist one lifecycle event with strict ID integrity.

    Returns True when the event is appended and False when the same
    lifecycle_event_id and canonical payload already exist. A conflicting
    payload for an existing ID raises LifecycleEventIntegrityError.
    """
    lifecycle_event_id = _validate_event(event)
    initialize_lifecycle_history(state)
    events = state[HISTORY_FIELD][EVENTS_FIELD]
    canonical = _canonical_event(event)

    for existing in events:
        if not isinstance(existing, dict):
            continue
        if existing.get("lifecycle_event_id") != lifecycle_event_id:
            continue

        existing_canonical = _canonical_event(existing)
        if existing_canonical == canonical:
            return False

        raise LifecycleEventIntegrityError(
            f"Conflicting lifecycle event payload for lifecycle_event_id={lifecycle_event_id!r}."
        )

    events.append(deepcopy(canonical))
    return True


def get_lifecycle_event(
    state: Dict[str, Any], lifecycle_event_id: str
) -> Optional[Dict[str, Any]]:
    """Return one persisted lifecycle event by stable ID, if present."""
    initialize_lifecycle_history(state)
    target = lifecycle_event_id.strip() if isinstance(lifecycle_event_id, str) else ""
    for event in state[HISTORY_FIELD][EVENTS_FIELD]:
        if isinstance(event, dict) and event.get("lifecycle_event_id") == target:
            return deepcopy(event)
    return None
