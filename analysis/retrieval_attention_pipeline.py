#!/usr/bin/env python3
"""Compose R7A/R7B attention generation with R7C proposal persistence."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from analysis.retrieval_attention_context import build_retrieval_attention_context
from analysis.retrieval_attention_policy import evaluate_retrieval_attention
from core.retrieval_attention_persistence import (
    append_retrieval_attention_proposal,
    initialize_retrieval_attention_history,
)
from core.retrieval_history_state import get_retrieval_history


def generate_and_persist_retrieval_attention(
    state: Dict[str, Any],
    policy: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate R7B proposals from persisted retrieval history and persist them.

    The adapter only composes already-defined R7A, R7B, and R7C layers. It does
    not perform retrieval, execute recommendations, transition lifecycle state,
    or modify scientific state.
    """
    if not isinstance(state, dict):
        raise TypeError("state must be a dictionary")
    if not isinstance(policy, dict):
        raise TypeError("policy must be a dictionary")

    initialize_retrieval_attention_history(state)

    history = get_retrieval_history(state)
    context = build_retrieval_attention_context(history)
    evaluation = evaluate_retrieval_attention(context, policy)

    persisted_count = 0
    duplicate_count = 0
    for proposal in evaluation.get("attention_items", []):
        stored = append_retrieval_attention_proposal(
            state,
            deepcopy(proposal),
        )
        if stored:
            persisted_count += 1
        else:
            duplicate_count += 1

    return {
        "context": context,
        "evaluation": evaluation,
        "persisted_count": persisted_count,
        "duplicate_count": duplicate_count,
    }
