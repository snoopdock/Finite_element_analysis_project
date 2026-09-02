#!/usr/bin/env python3
"""State adapter for append-only R7B attention-proposal persistence."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


HISTORY_FIELD = "retrieval_attention_history"
PROPOSALS_FIELD = "proposals"
REQUIRED_FIELDS = (
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


def initialize_retrieval_attention_history(state: Dict[str, Any]) -> None:
    """Ensure the attention-proposal history container exists."""
    history = state.get(HISTORY_FIELD)
    if not isinstance(history, dict):
        state[HISTORY_FIELD] = {PROPOSALS_FIELD: []}
        return

    proposals = history.get(PROPOSALS_FIELD)
    if not isinstance(proposals, list):
        history[PROPOSALS_FIELD] = []


def get_retrieval_attention_history(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return defensive copies of all persisted attention proposals."""
    initialize_retrieval_attention_history(state)
    proposals = state[HISTORY_FIELD][PROPOSALS_FIELD]
    return deepcopy([item for item in proposals if isinstance(item, dict)])


def has_retrieval_attention_proposal(
    state: Dict[str, Any],
    attention_id: str,
) -> bool:
    """Return whether a proposal with the given attention_id is persisted."""
    if not isinstance(attention_id, str) or not attention_id.strip():
        return False

    initialize_retrieval_attention_history(state)
    target = attention_id.strip()
    return any(
        isinstance(item, dict) and item.get("attention_id") == target
        for item in state[HISTORY_FIELD][PROPOSALS_FIELD]
    )


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_proposal(proposal: Dict[str, Any]) -> str:
    if not isinstance(proposal, dict):
        raise TypeError("Attention proposal must be a dictionary.")

    missing = [field for field in REQUIRED_FIELDS if field not in proposal]
    if missing:
        raise ValueError(
            "Attention proposal is missing required fields: " + ", ".join(missing)
        )

    attention_id = proposal.get("attention_id")
    if not isinstance(attention_id, str) or not attention_id.strip():
        raise ValueError("Attention proposal requires a non-empty attention_id.")

    if proposal.get("lifecycle_status") != "open":
        raise ValueError("New persisted R7B attention proposals must have lifecycle_status='open'.")

    event_ids = proposal.get("supporting_event_ids")
    if not isinstance(event_ids, list) or not event_ids or any(
        not isinstance(event_id, str) or not event_id.strip() for event_id in event_ids
    ):
        raise ValueError("Attention proposal requires non-empty supporting_event_ids.")

    return attention_id.strip()


def append_retrieval_attention_proposal(
    state: Dict[str, Any],
    proposal: Dict[str, Any],
    generated_at: Optional[str] = None,
) -> bool:
    """Persist one R7B proposal exactly once by attention_id.

    ``generated_at`` is persistence metadata only. It is not part of the
    deterministic R7B proposal core and may be supplied explicitly for tests
    or replayable persistence fixtures.

    Returns True when appended and False when the same attention_id already exists.
    """
    attention_id = _validate_proposal(proposal)
    initialize_retrieval_attention_history(state)

    if has_retrieval_attention_proposal(state, attention_id):
        return False

    timestamp = generated_at if generated_at is not None else _utc_timestamp()
    if not isinstance(timestamp, str) or not timestamp.strip():
        raise ValueError("generated_at must be a non-empty string when provided.")

    stored = deepcopy(proposal)
    stored["attention_id"] = attention_id
    stored["generated_at"] = timestamp.strip()
    state[HISTORY_FIELD][PROPOSALS_FIELD].append(stored)
    return True


def get_retrieval_attention_proposal(
    state: Dict[str, Any],
    attention_id: str,
) -> Optional[Dict[str, Any]]:
    """Return one persisted proposal by stable attention_id, if present."""
    initialize_retrieval_attention_history(state)
    target = attention_id.strip() if isinstance(attention_id, str) else ""
    for item in state[HISTORY_FIELD][PROPOSALS_FIELD]:
        if isinstance(item, dict) and item.get("attention_id") == target:
            return deepcopy(item)
    return None
