#!/usr/bin/env python3
"""Offline reconstruction of persisted R7B attention proposals."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, Mapping


DETERMINISTIC_FIELDS = (
    "attention_id",
    "policy_version",
    "query_scope",
    "provider",
    "attention_reason",
    "observed_condition",
    "lifecycle_status",
    "supporting_event_ids",
    "recommended_acquisition_action",
)

REQUIRED_FIELDS = DETERMINISTIC_FIELDS


def validate_persisted_proposal(proposal: Mapping[str, Any]) -> None:
    """Validate the structural shape of one persisted proposal."""
    if not isinstance(proposal, Mapping):
        raise TypeError("proposal must be a mapping")

    missing = [field for field in REQUIRED_FIELDS if field not in proposal]
    if missing:
        raise ValueError(
            "Persisted attention proposal is missing required fields: "
            + ", ".join(missing)
        )

    for field in REQUIRED_FIELDS:
        if field != "supporting_event_ids" and not isinstance(proposal[field], str):
            raise ValueError(f"{field} must be a string")

    event_ids = proposal["supporting_event_ids"]
    if not isinstance(event_ids, list) or not event_ids:
        raise ValueError("supporting_event_ids must be a non-empty list")
    if not all(isinstance(event_id, str) and event_id.strip() for event_id in event_ids):
        raise ValueError("supporting_event_ids must contain non-empty strings")


def _event_ids_from_history(history: Any) -> set[str]:
    if not isinstance(history, Iterable) or isinstance(history, (str, bytes, Mapping)):
        return set()
    result: set[str] = set()
    for event in history:
        if isinstance(event, Mapping):
            event_id = event.get("event_id")
            if isinstance(event_id, str) and event_id.strip():
                result.add(event_id.strip())
    return result


def validate_provenance(
    proposal: Mapping[str, Any],
    retrieval_history: Iterable[Mapping[str, Any]],
) -> None:
    """Verify all supporting retrieval-event references still resolve."""
    validate_persisted_proposal(proposal)
    available_ids = _event_ids_from_history(retrieval_history)
    missing = [
        event_id
        for event_id in proposal["supporting_event_ids"]
        if event_id.strip() not in available_ids
    ]
    if missing:
        raise ValueError(
            "Persisted attention proposal has missing supporting retrieval events: "
            + ", ".join(missing)
        )


def replay_persisted_proposal(
    proposal: Mapping[str, Any],
    retrieval_history: Iterable[Mapping[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Reconstruct a persisted proposal without rerunning R7B or retrieval."""
    validate_persisted_proposal(proposal)
    if retrieval_history is not None:
        validate_provenance(proposal, retrieval_history)

    return {
        field: deepcopy(proposal[field])
        for field in DETERMINISTIC_FIELDS
    }
