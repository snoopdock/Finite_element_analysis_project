#!/usr/bin/env python3
"""Read-only reconstruction of persisted retrieval-attention lifecycle history."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping


LIFECYCLE_REPLAY_SCHEMA_VERSION = 1
REQUIRED_EVENT_FIELDS = (
    "lifecycle_event_id",
    "attention_id",
    "previous_status",
    "new_status",
    "transition_reason",
    "created_at",
    "actor",
    "schema_version",
)
ALLOWED_STATES = {"open", "addressed", "closed"}
ALLOWED_TRANSITIONS = {
    (None, "open"),
    ("open", "addressed"),
    ("open", "closed"),
    ("addressed", "closed"),
}


class LifecycleReplayError(ValueError):
    """Raised when persisted lifecycle history cannot be replayed faithfully."""


def _validate_event_shape(event: Mapping[str, Any]) -> None:
    missing = [field for field in REQUIRED_EVENT_FIELDS if field not in event]
    if missing:
        raise LifecycleReplayError(
            "Lifecycle event is missing required fields: " + ", ".join(missing)
        )

    if not isinstance(event["lifecycle_event_id"], str) or not event["lifecycle_event_id"].strip():
        raise LifecycleReplayError("Lifecycle event requires a non-empty lifecycle_event_id.")
    if not isinstance(event["attention_id"], str) or not event["attention_id"].strip():
        raise LifecycleReplayError("Lifecycle event requires a non-empty attention_id.")
    if not isinstance(event["created_at"], str) or not event["created_at"].strip():
        raise LifecycleReplayError("Lifecycle event requires a non-empty created_at.")
    if not isinstance(event["actor"], str) or not event["actor"].strip():
        raise LifecycleReplayError("Lifecycle event requires a non-empty actor.")
    if not isinstance(event["transition_reason"], str) or not event["transition_reason"].strip():
        raise LifecycleReplayError("Lifecycle event requires a non-empty transition_reason.")

    previous = event["previous_status"]
    new = event["new_status"]
    if previous is not None and previous not in ALLOWED_STATES:
        raise LifecycleReplayError(f"Invalid previous_status: {previous!r}")
    if new not in ALLOWED_STATES:
        raise LifecycleReplayError(f"Invalid new_status: {new!r}")
    if (previous, new) not in ALLOWED_TRANSITIONS:
        raise LifecycleReplayError(
            f"Invalid lifecycle transition: {previous!r} -> {new!r}"
        )
    if event["schema_version"] != 1:
        raise LifecycleReplayError(
            f"Unsupported lifecycle event schema_version: {event['schema_version']!r}"
        )


def _event_sort_key(event: Mapping[str, Any]) -> tuple[str, str]:
    return (str(event["created_at"]), str(event["lifecycle_event_id"]))


def replay_retrieval_attention_lifecycle(
    events: Iterable[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Replay recorded lifecycle events without mutation, network, or recomputation."""
    if not isinstance(events, list):
        events = list(events)

    validated: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw_event in events:
        if not isinstance(raw_event, Mapping):
            raise TypeError("Lifecycle history entries must be mappings.")
        _validate_event_shape(raw_event)
        event = deepcopy(dict(raw_event))
        event_id = event["lifecycle_event_id"].strip()
        if event_id in seen_ids:
            raise LifecycleReplayError(
                f"Duplicate lifecycle_event_id in replay input: {event_id}"
            )
        seen_ids.add(event_id)
        event["lifecycle_event_id"] = event_id
        event["attention_id"] = event["attention_id"].strip()
        validated.append(event)

    ordered = sorted(validated, key=_event_sort_key)

    by_attention: Dict[str, List[Dict[str, Any]]] = {}
    for event in ordered:
        by_attention.setdefault(event["attention_id"], []).append(event)

    trajectories: List[Dict[str, Any]] = []
    for attention_id in sorted(by_attention, key=str.casefold):
        history = by_attention[attention_id]
        current_status = None
        transitions: List[Dict[str, Any]] = []
        for event in history:
            previous = event["previous_status"]
            new = event["new_status"]
            if previous != current_status:
                raise LifecycleReplayError(
                    "Lifecycle history is discontinuous for attention_id "
                    f"{attention_id!r}: expected previous_status {current_status!r}, "
                    f"received {previous!r}."
                )
            transitions.append(
                {
                    "lifecycle_event_id": event["lifecycle_event_id"],
                    "previous_status": previous,
                    "new_status": new,
                    "transition_reason": event["transition_reason"],
                    "created_at": event["created_at"],
                    "actor": event["actor"],
                }
            )
            current_status = new

        trajectories.append(
            {
                "attention_id": attention_id,
                "initial_status": transitions[0]["previous_status"],
                "final_status": current_status,
                "event_count": len(transitions),
                "transitions": transitions,
            }
        )

    return {
        "schema_version": LIFECYCLE_REPLAY_SCHEMA_VERSION,
        "event_count": len(ordered),
        "trajectories": trajectories,
    }
