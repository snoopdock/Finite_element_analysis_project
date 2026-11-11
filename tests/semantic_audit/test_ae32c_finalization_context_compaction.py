"""Regression tests for bounded AE-32C finalization-context rebuilding."""
from __future__ import annotations

import json

from audit_engine.semantic_audit.ae32c import InvestigationLimits
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
