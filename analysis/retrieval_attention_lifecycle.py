#!/usr/bin/env python3
"""Pure lifecycle-event model for retrieval-attention proposals.

R7D.2 creates and validates lifecycle transition records without persisting
state, mutating attention proposals, or executing acquisition actions.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping
from uuid import uuid4

from utils.text import utcnow


LIFECYCLE_EVENT_SCHEMA_VERSION = 1
ALLOWED_STATUSES = {"open", "addressed", "closed"}
ALLOWED_TRANSITIONS = {
    ("open", "addressed"),
    ("open", "closed"),
    ("addressed", "closed"),
}
INITIAL_TRANSITION = (None, "open")


class LifecycleTransitionError(ValueError):
    """Raised when a lifecycle status transition is not allowed."""


def validate_lifecycle_transition(
    previous_status: str | None,
    new_status: str,
) -> None:
    """Validate one lifecycle transition against the R7D.1 contract."""
    previous = None if previous_status is None else str(previous_status).strip().casefold()
    new = str(new_status).strip().casefold()

    if new not in ALLOWED_STATUSES:
        raise LifecycleTransitionError(
            f"invalid lifecycle status: {new_status!r}"
        )

    if previous is None:
        if INITIAL_TRANSITION != (None, new):
            raise LifecycleTransitionError(
                "initial lifecycle event must transition from null to open"
            )
        return

    if previous not in ALLOWED_STATUSES:
        raise LifecycleTransitionError(
            f"invalid previous lifecycle status: {previous_status!r}"
        )

    if (previous, new) not in ALLOWED_TRANSITIONS:
        raise LifecycleTransitionError(
            f"forbidden lifecycle transition: {previous} -> {new}"
        )


def create_lifecycle_event(
    attention_id: str,
    previous_status: str | None,
    new_status: str,
    transition_reason: str,
    actor: str,
    *,
    lifecycle_event_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Create one validated lifecycle event without mutating caller data."""
    if not isinstance(attention_id, str) or not attention_id.strip():
        raise ValueError("attention_id must be a non-empty string")
    if not isinstance(transition_reason, str) or not transition_reason.strip():
        raise ValueError("transition_reason must be a non-empty string")
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("actor must be a non-empty string")

    validate_lifecycle_transition(previous_status, new_status)

    event_id = lifecycle_event_id
    if event_id is None:
        event_id = f"lifecycle-{uuid4()}"
    elif not isinstance(event_id, str) or not event_id.strip():
        raise ValueError("lifecycle_event_id must be a non-empty string")

    timestamp = created_at if created_at is not None else utcnow()
    if not isinstance(timestamp, str) or not timestamp.strip():
        raise ValueError("created_at must be a non-empty string")

    previous = None if previous_status is None else str(previous_status).strip().casefold()
    new = str(new_status).strip().casefold()

    return {
        "lifecycle_event_id": event_id.strip(),
        "attention_id": attention_id.strip(),
        "previous_status": previous,
        "new_status": new,
        "transition_reason": transition_reason.strip(),
        "created_at": timestamp.strip(),
        "actor": actor.strip(),
        "schema_version": LIFECYCLE_EVENT_SCHEMA_VERSION,
    }


def validate_lifecycle_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and defensively copy a lifecycle event."""
    if not isinstance(event, Mapping):
        raise TypeError("event must be a mapping")

    required = {
        "lifecycle_event_id",
        "attention_id",
        "previous_status",
        "new_status",
        "transition_reason",
        "created_at",
        "actor",
        "schema_version",
    }
    missing = sorted(required - set(event))
    if missing:
        raise ValueError(f"missing lifecycle event fields: {missing}")

    if event["schema_version"] != LIFECYCLE_EVENT_SCHEMA_VERSION:
        raise ValueError("unsupported lifecycle event schema version")

    for field in ("lifecycle_event_id", "attention_id", "created_at", "actor"):
        if not isinstance(event[field], str) or not event[field].strip():
            raise ValueError(f"{field} must be a non-empty string")

    if not isinstance(event["transition_reason"], str) or not event["transition_reason"].strip():
        raise ValueError("transition_reason must be a non-empty string")

    previous_status = event["previous_status"]
    if previous_status is not None and not isinstance(previous_status, str):
        raise ValueError("previous_status must be null or a string")
    if not isinstance(event["new_status"], str):
        raise ValueError("new_status must be a string")

    validate_lifecycle_transition(previous_status, event["new_status"])
    return deepcopy(dict(event))


__all__ = [
    "ALLOWED_STATUSES",
    "ALLOWED_TRANSITIONS",
    "INITIAL_TRANSITION",
    "LIFECYCLE_EVENT_SCHEMA_VERSION",
    "LifecycleTransitionError",
    "create_lifecycle_event",
    "validate_lifecycle_event",
    "validate_lifecycle_transition",
]
