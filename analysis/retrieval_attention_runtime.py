#!/usr/bin/env python3
"""Live-cycle connector for retrieval attention; process-only, no execution authority."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from analysis.retrieval_attention_pipeline import (
    generate_and_persist_retrieval_attention,
)


POLICY_CONFIG_FIELD = "retrieval_attention"
REQUIRED_POLICY_FIELDS = (
    "policy_version",
    "history_window_events",
    "repeated_non_success_threshold",
    "repeated_empty_result_threshold",
)


def get_retrieval_attention_policy(config: Dict[str, Any]) -> Dict[str, Any]:
    """Build the explicit R7B policy from configuration without hidden defaults."""
    if not isinstance(config, dict):
        raise TypeError("config must be a dictionary")

    raw = config.get(POLICY_CONFIG_FIELD)
    if not isinstance(raw, dict):
        raise ValueError(
            "retrieval_attention configuration is required for live attention processing."
        )

    missing = [field for field in REQUIRED_POLICY_FIELDS if field not in raw]
    if missing:
        raise ValueError(
            "retrieval_attention configuration is missing required fields: "
            + ", ".join(missing)
        )

    return {
        field: deepcopy(raw[field])
        for field in REQUIRED_POLICY_FIELDS
    }


def process_live_retrieval_attention(
    state: Dict[str, Any],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """Compose R7A-R7C for the current live state.

    This connector performs no network retrieval, LLM calls, lifecycle
    transitions, or acquisition-action execution. Errors are intentionally
    allowed to propagate to the caller so the live pipeline can record them as
    operational attention-processing errors without treating them as
    scientific conclusions.
    """
    policy = get_retrieval_attention_policy(config)
    result = generate_and_persist_retrieval_attention(state, policy)
    return {
        "status": "success",
        "policy_version": policy["policy_version"],
        "persisted_count": int(result.get("persisted_count", 0)),
        "duplicate_count": int(result.get("duplicate_count", 0)),
        "evaluation": result.get("evaluation", {}),
    }
