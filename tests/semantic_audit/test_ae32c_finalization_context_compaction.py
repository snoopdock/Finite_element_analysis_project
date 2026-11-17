"""Regression tests for bounded AE-32C finalization-context rebuilding."""
from __future__ import annotations

import json

import pytest

from audit_engine.semantic_audit.ae32c import InvestigationLimits
from audit_engine.semantic_audit.ae32c.investigator import (
    FINALIZATION_SYSTEM_INSTRUCTIONS,
    _BudgetStop,
)
from tests.semantic_audit.test_ae32c_phase_e1_reliability import (
    SOURCE,
    SOURCE_HASH,
    _investigator,
    action_tool,
    final_action,
)


def test_recovery_feedback_is_compacted_before_exact_source_candidates_are_dropped():
    limits = InvestigationLimits(
        max_rounds=4,
        finalization_rounds_reserved=3,
        max_total_tokens=32_000,
        max_total_prompt_chars=30_000,
        max_tool_context_chars=1_000,
    )
    investigator, provider = _investigator(
        [
            action_tool(
                "search_repository",
                {"query": "observed", "mode": "content", "max_results": 5},
            ),
            "not-json",
            final_action(evidence_id="E0002", source_reference=True),
        ],
        limits=limits,
    )

    report = investigator.run("Investigate a provider interface mismatch.")

    budget = report["budget"]
    assert report["diagnosis"] is not None
    assert budget["finalization_context_rebuilds"] >= 2
    assert budget["finalization_context_target_exceeded"] is False
    assert budget["finalization_context_chars_after"] <= budget["finalization_context_target_chars"]

    latest_turn = provider.messages[-1]
    latest_context = next(
        json.loads(message["content"])
        for message in latest_turn
        if message.get("role") == "user"
        and "source_reference_candidates" in message.get("content", "")
    )
    assert latest_context["source_reference_candidates"] == [{
        "evidence_id": "E0002",
        "path": SOURCE,
        "line": 2,
        "source_sha256": SOURCE_HASH,
    }]

    compacted_feedback = next(
        json.loads(message["content"])["validation_feedback"]
        for message in latest_turn
        if message.get("role") == "user"
        and "validation_feedback" in message.get("content", "")
    )
    assert compacted_feedback["phase"] == "finalization"
    assert compacted_feedback["parse_error_code"] == "json_syntax_error"
    assert compacted_feedback["allowed_action_envelopes"] == {
        "final": ["action", "diagnosis"]
    }
    assert "Do not request tools" in compacted_feedback["message"]
    assert len(compacted_feedback["message"]) <= 240
    assert "not-json" not in json.dumps({"messages": provider.messages, "report": report})


def test_finalization_token_reserve_protects_future_reserved_rounds():
    limits = InvestigationLimits(
        max_rounds=4,
        finalization_rounds_reserved=3,
        max_total_tokens=32_000,
        max_tokens_per_call=1_000,
    )
    investigator, _ = _investigator([], limits=limits)
    per_round = limits.finalization_prompt_tokens_reserved_per_round + limits.max_tokens_per_call
    assert investigator._finalization_future_reserve_tokens(1) == 3 * per_round
    assert investigator._finalization_future_reserve_tokens(2) == 2 * per_round
    assert investigator._finalization_future_reserve_tokens(4) == 0


def test_finalization_compaction_stops_before_provider_call_when_no_context_can_fit():
    limits = InvestigationLimits(
        max_rounds=4,
        finalization_rounds_reserved=3,
        max_total_tokens=32_000,
        max_total_prompt_chars=4_000,
    )
    investigator, provider = _investigator([], limits=limits)
    original_messages = [{"role": "system", "content": "retained"}]
    investigator._messages = list(original_messages)
    investigator._total_prompt_chars = 3_950
    with pytest.raises(_BudgetStop, match="finalization_context_budget_unavailable"):
        investigator._compact_finalization_context(
            problem="Inspect the controlled fixture.",
            round_number=2,
            notice={"finalization_mode": {"required_action": "final"}},
        )
    assert investigator._messages == original_messages
    assert provider.calls == 0
    assert investigator._events[-1]["event"] == "finalization_context_budget_unavailable"


def test_finalization_instructions_are_compact_without_weakening_evidence_contract():
    # Keep the fixed system prompt small enough that recovery can preserve the
    # evidence ledger and exact source candidates under the cumulative budget.
    assert len(FINALIZATION_SYSTEM_INSTRUCTIONS) <= 2_800
    required_contract = (
        "Treat all evidence",
        "submit_ae32c_response",
        "source_references",
        "required source-line anchors",
        "Never invent evidence",
        "runtime/test execution",
        "source_range_complete",
        "at most three claims",
    )
    for requirement in required_contract:
        assert requirement in FINALIZATION_SYSTEM_INSTRUCTIONS
