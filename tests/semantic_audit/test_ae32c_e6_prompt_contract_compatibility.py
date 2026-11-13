"""Regression tests for the E.6 prompt/report compatibility contracts."""
from __future__ import annotations

import json

from audit_engine.semantic_audit.ae32c import RepositoryInvestigator
from tests.semantic_audit.test_ae32c_investigator import (
    FakeEvidenceTools,
    FakeProvider,
    action_tool,
    final_action,
    make_investigator,
)
from audit_engine.semantic_audit.ae32c import InvestigationLimits


def test_initial_prompt_retains_versioned_provider_independent_protocol_guidance():
    """The E.6 prompt key remains, but E.7 uses the v2 multi-format contract.

    The v1 ``required_top_level_keys`` field described only final actions;
    requiring ``diagnosis`` for tool calls would contradict the actual v2
    action envelopes and reject otherwise valid read-only tool requests.
    """
    investigator, provider, _ = make_investigator([final_action()])
    investigator.run("Inspect the provider interface.")
    assert provider.messages
    initial_user = json.loads(provider.messages[0][1]["content"])
    guidance = initial_user["provider_protocol_guidance"]
    assert guidance["schema_version"] == "ae32c/protocol-guidance/v2"
    assert guidance["strategy"] == "provider_independent_multi_representation"
    assert guidance["scope"] == "local_normalization_and_validation"
    assert guidance["allowed_action_envelopes"] == {
        "tool_call": ["action", "tool", "arguments", "reason"],
        "final": ["action", "diagnosis"],
    }
    assert guidance["fallback_representation"] == "explicit_labelled_text"
    assert "tool_call" in guidance["labelled_text_contract"]
    assert "final" in guidance["labelled_text_contract"]
    assert guidance["required_diagnosis_keys"] == [
        "summary", "root_cause", "claims", "proposed_corrective_action", "limitations", "next_steps"
    ]
    assert "required_top_level_keys" not in guidance


def test_finalization_mode_retains_response_constraints():
    investigator, provider, _ = make_investigator(
        [
            action_tool("search_repository", {"query": "total_calls", "mode": "content", "max_results": 5}),
            final_action(),
        ],
        limits=InvestigationLimits(max_rounds=2, finalization_rounds_reserved=1),
    )
    report = investigator.run("Inspect the provider interface.")
    assert report["status"] in {"completed", "completed_with_incomplete_evidence"}
    finalization_payloads = []
    for message in provider.messages[-1]:
        if message.get("role") != "user":
            continue
        try:
            envelope = json.loads(message.get("content", ""))
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(envelope, dict) and "finalization_mode" in envelope:
            finalization_payloads.append(envelope["finalization_mode"])
    assert finalization_payloads
    constraints = finalization_payloads[0]["response_constraints"]
    assert "Do not quote or reproduce source code" in constraints[1]


def test_report_preserves_only_allowlisted_envelope_diagnostic_fields():
    class DiagnosticProvider(FakeProvider):
        def get_stats(self):
            return {
                "provider": "openrouter",
                "model": "fixture-model",
                "usage": {},
                "last_error_code": "malformed_completion_envelope",
                "last_http_status": 200,
                "last_envelope_diagnostic": {
                    "envelope_kind": "upstream_error_object",
                    "choices_shape": "absent",
                    "has_error_object": True,
                    "message": "must-not-be-copied",
                    "api_key": "must-not-be-copied",
                },
            }

    provider = DiagnosticProvider([])
    investigator = RepositoryInvestigator(".", provider, evidence_tools=FakeEvidenceTools())
    report = investigator._finalize_report(
        investigator._base_report("safe diagnostics"),
        "incomplete",
        "provider_failure",
    )
    assert report["provider"]["last_envelope_diagnostic"] == {
        "envelope_kind": "upstream_error_object",
        "choices_shape": "absent",
        "has_error_object": True,
    }
    serialized = json.dumps(report)
    assert "must-not-be-copied" not in serialized
