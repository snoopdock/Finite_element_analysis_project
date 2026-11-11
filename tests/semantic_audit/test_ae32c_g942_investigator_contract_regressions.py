"""Regression tests for stable AE-32C investigator prompt/report contracts."""
from __future__ import annotations

import json

from audit_engine.semantic_audit.ae32c import RepositoryInvestigator
from tests.semantic_audit.test_ae32c_investigator import FakeEvidenceTools, FakeProvider


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
