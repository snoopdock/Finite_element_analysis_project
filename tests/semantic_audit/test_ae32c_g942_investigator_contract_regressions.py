"""Regression tests for stable AE-32C investigator prompt/report contracts."""
from __future__ import annotations

import json

from audit_engine.semantic_audit.ae32c import InvestigationLimits, RepositoryInvestigator
from tests.semantic_audit.test_ae32c_investigator import (
    FakeEvidenceTools,
    FakeProvider,
    action_tool,
    final_action,
    make_investigator,
)


def _initial_payload(provider):
    for message in provider.messages[0]:
        if message.get("role") == "user":
            try:
                payload = json.loads(message.get("content", ""))
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict) and "provider_protocol_guidance" in payload:
                return payload
    raise AssertionError("initial provider protocol guidance was not sent")


def test_protocol_guidance_declares_exact_action_envelopes_and_concise_rule():
    provider = FakeProvider(["{}"])
    provider.provider_name = "nararouter"
    provider.model = "historical-fixture-model"
    investigator = RepositoryInvestigator(
        ".",
        provider,
        provider_name="nararouter",
        model_name="historical-fixture-model",
        evidence_tools=FakeEvidenceTools(),
    )
    investigator.run("Inspect the provider interface.")
    guidance = _initial_payload(provider)["provider_protocol_guidance"]

    assert guidance["allowed_action_envelopes"] == {
        "tool_call": ["action", "tool", "arguments", "reason"],
        "final": ["action", "diagnosis"],
    }
    assert any("Keep responses concise" in rule for rule in guidance["rules"])


def test_http_error_report_keeps_safe_category_and_request_id_only():
    class DiagnosticProvider(FakeProvider):
        def get_stats(self):
            return {
                "provider": "nararouter",
                "model": "fixture-model",
                "usage": {},
                "last_error_code": "provider_api_error_payload",
                "last_http_status": 400,
                "last_http_error_diagnostic": {
                    "http_status": 400,
                    "body_status": "json",
                    "body_shape": "object",
                    "error_shape": "object",
                    "error_type": "invalid_request_error",
                    "error_code": "model_not_found",
                    "error_param": "model",
                    "error_message_category": "provider_internal_error",
                    "error_request_id": "req-12345",
                    "error_fields": ["type", "code", "param", "message"],
                    "top_level_error_fields": [],
                    "message": "must-not-be-copied",
                    "api_key": "must-not-be-copied-either",
                },
                "last_envelope_diagnostic": {
                    "envelope_kind": "upstream_error_object",
                    "choices_shape": "absent",
                    "has_error_object": True,
                    "message": "must-not-be-copied",
                },
            }

    provider = DiagnosticProvider([])
    investigator = RepositoryInvestigator(
        ".",
        provider,
        provider_name="nararouter",
        model_name="fixture-model",
        evidence_tools=FakeEvidenceTools(),
    )
    report = investigator._finalize_report(
        investigator._base_report("safe diagnostics"),
        "incomplete",
        "provider_failure",
    )
    safe = report["provider"]["last_http_error_diagnostic"]

    assert safe["error_code"] == "model_not_found"
    assert safe["error_message_category"] == "provider_internal_error"
    assert safe["error_request_id"] == "req-12345"
    serialized = json.dumps(report)
    assert "must-not-be-copied" not in serialized
    assert "must-not-be-copied-either" not in serialized


def test_provider_guidance_does_not_assume_provider_enforced_json_mode():
    provider = FakeProvider(["{}"])
    provider.provider_name = "nararouter"
    provider.model = "fixture-model"
    investigator = RepositoryInvestigator(
        ".",
        provider,
        provider_name="nararouter",
        model_name="fixture-model",
        evidence_tools=FakeEvidenceTools(),
    )
    investigator.run("Inspect the provider interface.")
    guidance = _initial_payload(provider)["provider_protocol_guidance"]
    assert any(
        "Provider-enforced JSON mode is not assumed" in rule
        for rule in guidance["rules"]
    )
    assert any(
        "validated locally" in rule
        for rule in guidance["rules"]
    )


def test_provider_independent_guidance_is_shared_across_adapters():
    provider = FakeProvider(["{}"])
    provider.provider_name = "cloudflare"
    provider.model = "fixture-model"
    investigator = RepositoryInvestigator(
        ".",
        provider,
        provider_name="cloudflare",
        model_name="fixture-model",
        evidence_tools=FakeEvidenceTools(),
    )
    investigator.run("Inspect the provider interface.")
    guidance = _initial_payload(provider)["provider_protocol_guidance"]
    assert any(
        "Provider-enforced JSON mode is not assumed" in rule
        for rule in guidance["rules"]
    )


def test_nararouter_invalid_json_recovery_includes_explicit_non_assumed_json_mode_contract():
    provider = FakeProvider([
        "not-json",
        action_tool("search_repository", {"query": "observed", "mode": "content", "max_results": 5}),
        final_action(evidence_id="E0002", source_reference=True),
    ])
    provider.provider_name = "nararouter"
    provider.model = "laguna-s-2.1"
    tools = FakeEvidenceTools()
    investigator = RepositoryInvestigator(
        ".",
        provider,
        provider_name="nararouter",
        model_name="laguna-s-2.1",
        evidence_tools=tools,
        limits=InvestigationLimits(max_rounds=5, finalization_rounds_reserved=1),
        id_factory=lambda: "nararouter-json-contract-regression",
    )

    report = investigator.run("Investigate the observed provider interface issue")
    assert report["status"] == "completed_with_incomplete_evidence"
    initial_user = next(
        json.loads(message["content"])
        for message in provider.messages[0]
        if message.get("role") == "user"
        and '"provider_protocol_guidance"' in message.get("content", "")
    )
    guidance = initial_user["provider_protocol_guidance"]
    assert guidance["allowed_action_envelopes"]["tool_call"] == [
        "action", "tool", "arguments", "reason"
    ]
    assert guidance["allowed_action_envelopes"]["final"] == [
        "action", "diagnosis"
    ]
    assert any(
        "Provider-enforced JSON mode is not assumed" in rule
        for rule in guidance["rules"]
    )

    recovery_feedback = []
    for batch in provider.messages:
        for message in batch:
            if message.get("role") != "user":
                continue
            try:
                envelope = json.loads(message.get("content", ""))
            except (TypeError, json.JSONDecodeError):
                continue
            feedback = envelope.get("validation_feedback") if isinstance(envelope, dict) else None
            if (
                isinstance(feedback, dict)
                and feedback.get("schema_version") == "ae32c/json-validation-feedback/v1"
            ):
                recovery_feedback.append(feedback)

    assert recovery_feedback
    feedback = recovery_feedback[0]
    assert feedback["allowed_action_envelopes"] == {
        "tool_call": ["action", "tool", "arguments", "reason"],
        "final": ["action", "diagnosis"],
    }
    assert feedback["parse_error_code"] == "json_syntax_error"
    assert feedback["parse_error_line"] == 1
    assert feedback["parse_error_column"] == 1
    assert feedback["json_syntax_rules"]
    assert "double quotes" in feedback["json_syntax_rules"][0]
    assert all(isinstance(rule, str) and rule for rule in feedback["json_syntax_rules"])
    # Recovery feedback may expose parser position and static rules, never malformed output.
    assert "not-json" not in json.dumps(feedback)


def test_finalization_json_recovery_only_advertises_final_action_envelope():
    limits = InvestigationLimits(
        max_rounds=4,
        finalization_rounds_reserved=3,
        max_invalid_json_retries=2,
        max_finalization_invalid_json_retries=2,
        max_tool_calls=5,
        max_tokens_per_call=1_000,
        max_total_tokens=32_000,
        max_total_prompt_chars=500_000,
        max_elapsed_seconds=30,
    )
    investigator, provider, _ = make_investigator(
        [
            action_tool("search_repository", {"query": "observed", "mode": "content", "max_results": 5}),
            "not-json finalization response",
            final_action(evidence_id="E0002", source_reference=True),
        ],
        limits=limits,
    )
    report = investigator.run("Investigate a failed workflow")
    assert report["diagnosis"] is not None

    feedback_items = []
    for turn in provider.messages:
        for message in turn:
            if message.get("role") != "user":
                continue
            try:
                envelope = json.loads(message.get("content", ""))
            except (TypeError, json.JSONDecodeError):
                continue
            feedback = envelope.get("validation_feedback") if isinstance(envelope, dict) else None
            if (
                isinstance(feedback, dict)
                and feedback.get("schema_version") == "ae32c/json-validation-feedback/v1"
                and feedback.get("phase") == "finalization"
            ):
                feedback_items.append(feedback)

    assert feedback_items
    assert feedback_items[0]["allowed_action_envelopes"] == {
        "final": ["action", "diagnosis"]
    }
    assert "tool_call" not in feedback_items[0]["allowed_action_envelopes"]
    assert "not-json finalization response" not in json.dumps(feedback_items)

