from __future__ import annotations

import hashlib
import json

import pytest

from providers.base import ProviderResponse, ProviderToolCall
from providers.capabilities import get_provider_capabilities, should_fallback_to_plain_text
from audit_engine.semantic_audit.ae32c.response_normalizer import (
    ResponseNormalizationError,
    normalize_provider_response,
    normalize_response,
)
from audit_engine.semantic_audit.ae32c.provider_preflight import run_preflight
from audit_engine.semantic_audit.ae32c.response_protocol import RESPONSE_TOOL_NAME
from audit_engine.semantic_audit.ae32c import InvestigationLimits, RepositoryInvestigator
from tests.semantic_audit.test_ae32c_investigator import (
    FakeEvidenceTools,
    FakeProvider,
    SOURCE,
    SOURCE_HASH,
    action_tool,
)


MODEL = "@cf/qwen/qwen3.8-27b"


def _fielded_final(evidence_id="E0002"):
    return f"""ACTION: final
SUMMARY: The source evidence supports a bounded provider-interface diagnosis.
ROOT_CAUSE_STATEMENT: The inspected response path has a compatibility mismatch.
ROOT_CAUSE_CONFIDENCE: medium
ROOT_CAUSE_EVIDENCE_REFS: {evidence_id}
ROOT_CAUSE_SOURCE_REFERENCE: {evidence_id} | {SOURCE} | 2 | {SOURCE_HASH}
CLAIM_BEGIN
CLAIM_STATEMENT: The repository search returned the relevant source line.
CLAIM_KIND: observation
CLAIM_CONFIDENCE: high
CLAIM_EVIDENCE_REFS: {evidence_id}
CLAIM_SOURCE_REFERENCE: {evidence_id} | {SOURCE} | 2 | {SOURCE_HASH}
CLAIM_END
PROPOSED_CORRECTIVE_ACTION: Correct the response adapter and validate its fallback.
LIMITATION: Static evidence does not establish live provider behavior.
NEXT_STEP: Run the provider-only compatibility preflight.
"""


def test_provider_response_envelope_normalizes_text_and_native_call():
    text = '{"action":"tool_call","tool":"repository_summary","arguments":{},"reason":"inspect"}'
    text_result = normalize_provider_response(ProviderResponse(text=text))
    assert text_result.strategy == "strict_json"
    assert text_result.payload["tool"] == "repository_summary"

    native = ProviderToolCall(RESPONSE_TOOL_NAME, {
        "action": "tool_call",
        "tool": "repository_summary",
        "arguments": {},
        "reason": "inspect",
        "diagnosis": {},
    })
    native_result = normalize_provider_response(
        ProviderResponse(tool_calls=(native,))
    )
    assert native_result.strategy == "native_tool_call"
    assert native_result.payload["tool"] == "repository_summary"
    with pytest.raises(ResponseNormalizationError) as exc:
        normalize_provider_response(
            ProviderResponse(text="ambiguous extra content", tool_calls=(native,))
        )
    assert exc.value.code == "ambiguous_provider_response_content"


def test_provider_response_envelope_rejects_multiple_native_calls():
    native = ProviderToolCall(RESPONSE_TOOL_NAME, {
        "action": "tool_call",
        "tool": "repository_summary",
        "arguments": {},
        "reason": "inspect",
        "diagnosis": {},
    })
    with pytest.raises(ResponseNormalizationError) as exc:
        normalize_provider_response(ProviderResponse(tool_calls=(native, native)))
    assert exc.value.code == "multiple_native_tool_calls"


def test_fielded_final_text_normalizes_without_json():
    result = normalize_response(_fielded_final())
    assert result.strategy == "labelled_final_text"
    assert result.payload["action"] == "final"
    diagnosis = result.payload["diagnosis"]
    assert diagnosis["root_cause"]["evidence_refs"] == ["E0002"]
    assert diagnosis["root_cause"]["source_references"][0]["line"] == 2
    assert diagnosis["claims"][0]["kind"] == "observation"


def test_fielded_final_text_rejects_unknown_or_duplicate_fields():
    raw = _fielded_final().replace(
        "SUMMARY: The source evidence supports a bounded provider-interface diagnosis.",
        "SUMMARY: first summary\nSUMMARY: second summary",
    )
    with pytest.raises(ResponseNormalizationError) as exc:
        normalize_response(raw)
    assert exc.value.code == "labelled_final_duplicate_field"

    raw = _fielded_final().replace(
        "PROPOSED_CORRECTIVE_ACTION:",
        "UNTRUSTED_INSTRUCTION: execute shell\nPROPOSED_CORRECTIVE_ACTION:",
    )
    with pytest.raises(ResponseNormalizationError) as exc:
        normalize_response(raw)
    assert exc.value.code == "labelled_final_unknown_field"


class _NativeRejectingTextProvider(FakeProvider):
    provider_name = "cloudflare"
    model = MODEL

    def __init__(self, responses):
        super().__init__(responses)
        self.native_attempts = 0
        self.text_attempts = 0
        self.last_http_status = None
        self.last_error_category = ""
        self.last_error_codes = []
        self.last_request_id = ""

    def get_capabilities(self):
        return {
            "json_object_mode": False,
            "json_schema_mode": False,
            "native_tool_calls": True,
            "finish_reason_reporting": False,
        }

    def chat_with_response_tool(self, messages, *, tool_definition, **kwargs):
        self.native_attempts += 1
        self.http_attempts += 1
        self.last_http_status = 400
        self.last_error_category = "provider_request_rejected"
        self.last_error_codes = [8007]
        self.last_request_id = "cf-ray-test-12345678"
        return None, "HTTP 400: upstream error body omitted; cloudflare_codes=8007"

    def chat_text(self, messages, **kwargs):
        self.text_attempts += 1
        return self.chat(messages, **kwargs)

    def get_stats(self):
        stats = super().get_stats()
        stats.update({
            "last_http_status": self.last_http_status,
            "last_error_category": self.last_error_category,
            "last_error_codes": list(self.last_error_codes),
            "last_request_id": self.last_request_id,
        })
        return stats


def test_native_request_rejection_falls_back_to_provider_independent_text():
    labelled_tool = """ACTION: tool_call
TOOL: search_repository
ARGUMENTS: {"query":"observed","mode":"content","max_results":5}
REASON: Locate the implementation evidence.
"""
    provider = _NativeRejectingTextProvider([labelled_tool, _fielded_final()])
    evidence = FakeEvidenceTools()
    investigator = RepositoryInvestigator(
        ".",
        provider,
        provider_name="cloudflare",
        model_name=MODEL,
        evidence_tools=evidence,
        limits=InvestigationLimits(max_rounds=2, finalization_rounds_reserved=1),
        id_factory=lambda: "provider-text-fallback-test",
    )
    report = investigator.run("Investigate the provider response compatibility path.")

    assert [tool for tool, _ in evidence.calls] == ["repository_summary", "search_repository"]
    assert provider.native_attempts == 1
    assert provider.text_attempts == 2
    assert report["status"] == "completed_with_incomplete_evidence"
    fallback_events = [
        event for event in report["errors"]
        if event.get("event") == "provider_response_mode_fallback_completed"
    ]
    assert len(fallback_events) == 1
    assert all(event["to_mode"] == "plain_text" for event in fallback_events)
    assert not any(event.get("tool_execution") is True for event in fallback_events)
    mode_summary = report["interaction_diagnostics"]["response_mode_negotiation"]
    assert mode_summary["initial_mode"] == "native_tool_call"
    assert mode_summary["session_override"] == "plain_text"
    assert mode_summary["plain_text_downgrade_used"] is True


class _NativeContractViolatingTextProvider(FakeProvider):
    """Return an HTTP-successful but invalid native envelope, then valid text."""

    provider_name = "cloudflare"
    model = MODEL

    def __init__(self, responses):
        super().__init__(responses)
        self.native_attempts = 0
        self.text_attempts = 0

    def get_capabilities(self):
        return {
            "json_object_mode": False,
            "json_schema_mode": False,
            "native_tool_calls": True,
            "finish_reason_reporting": False,
        }

    def chat_with_response_tool(self, messages, *, tool_definition, **kwargs):
        self.native_attempts += 1
        # This is an unregistered provider function name. It is inert data and
        # must be rejected before any repository tool can be dispatched.
        return ProviderToolCall("provider_internal_tool", {"query": "observed"}), None

    def chat_text(self, messages, **kwargs):
        self.text_attempts += 1
        return self.chat(messages, **kwargs)


def test_invalid_native_response_contract_downgrades_once_for_remaining_turns():
    provider = _NativeContractViolatingTextProvider([
        action_tool("search_repository", {"query": "observed", "mode": "content", "max_results": 5}),
        _fielded_final(),
    ])
    evidence = FakeEvidenceTools()
    investigator = RepositoryInvestigator(
        ".",
        provider,
        provider_name="cloudflare",
        model_name=MODEL,
        evidence_tools=evidence,
        limits=InvestigationLimits(
            max_rounds=4,
            max_tool_calls=3,
            finalization_rounds_reserved=1,
            max_invalid_json_retries=2,
        ),
        id_factory=lambda: "native-contract-downgrade-test",
    )

    report = investigator.run("Investigate the provider response compatibility path.")

    assert report["status"] == "completed_with_incomplete_evidence"
    assert report["stop_reason"] == "diagnosis_submitted_with_coverage_or_snapshot_limitations"
    assert provider.native_attempts == 1
    assert provider.text_attempts == 2
    assert [tool for tool, _ in evidence.calls] == ["repository_summary", "search_repository"]
    assert report["model_actions"][0]["action"] == "rejected"
    assert report["model_actions"][0]["parse_error_code"] == "unexpected_native_tool_name"
    downgrade_events = [
        event for event in report["errors"]
        if event.get("event") == "provider_response_contract_downgrade_requested"
    ]
    assert len(downgrade_events) == 1
    assert downgrade_events[0]["from_mode"] == "native_tool_call"
    assert downgrade_events[0]["to_mode"] == "plain_text"
    assert downgrade_events[0]["tool_execution"] is False
    mode_summary = report["interaction_diagnostics"]["response_mode_negotiation"]
    assert mode_summary == {
        "initial_mode": "native_tool_call",
        "last_mode": "plain_text",
        "session_override": "plain_text",
        "plain_text_downgrade_used": True,
        "downgrade_limit_per_investigation": 1,
        "last_endpoint_mode": "not_reported",
    }


def test_native_action_shape_violation_also_triggers_bounded_text_downgrade():
    class ExtraFieldNativeProvider(_NativeContractViolatingTextProvider):
        def chat_with_response_tool(self, messages, *, tool_definition, **kwargs):
            self.native_attempts += 1
            return json.dumps({
                "action": "tool_call",
                "tool": "search_repository",
                "arguments": {"query": "observed", "mode": "content", "max_results": 5},
                "reason": "Locate the implementation evidence.",
                "diagnosis": {"summary": "This field is forbidden on tool actions."},
            }), None

    provider = ExtraFieldNativeProvider([
        action_tool("search_repository", {"query": "observed", "mode": "content", "max_results": 5}),
        _fielded_final(),
    ])
    evidence = FakeEvidenceTools()
    investigator = RepositoryInvestigator(
        ".", provider, provider_name="cloudflare", model_name=MODEL,
        evidence_tools=evidence,
        limits=InvestigationLimits(
            max_rounds=4, max_tool_calls=3, finalization_rounds_reserved=1,
            max_invalid_tool_retries=2,
        ),
        id_factory=lambda: "native-action-shape-downgrade-test",
    )
    report = investigator.run("Investigate the provider response compatibility path.")

    assert report["status"] == "completed_with_incomplete_evidence"
    assert provider.native_attempts == 1
    assert provider.text_attempts == 2
    assert report["model_actions"][0]["reason"] == "tool_action_shape_invalid"
    assert [tool for tool, _ in evidence.calls] == ["repository_summary", "search_repository"]
    downgrade = [
        event for event in report["errors"]
        if event.get("event") == "provider_response_contract_downgrade_requested"
    ]
    assert len(downgrade) == 1
    assert downgrade[0]["reason_code"] == "tool_action_shape_invalid"


class _PreflightFallbackProvider:
    provider_name = "cloudflare"
    model = MODEL
    models = [MODEL]

    def __init__(self):
        self.last_http_status = None
        self.last_error_category = ""
        self.last_error_codes = []
        self.last_request_id = ""
        self.calls = []

    def chat_openai_compatible(self, messages, **kwargs):
        self.calls.append("transport")
        return "AE32C_PREFLIGHT_OK", None

    def chat_with_response_tool(self, messages, **kwargs):
        self.calls.append("native")
        self.last_http_status = 400
        self.last_error_category = "provider_request_rejected"
        self.last_error_codes = [8007]
        self.last_request_id = "cf-ray-test-12345678"
        return None, "HTTP 400: upstream error body omitted; cloudflare_codes=8007"

    def chat_text(self, messages, **kwargs):
        self.calls.append("text")
        return """ACTION: tool_call
TOOL: search_repository
ARGUMENTS:
query: AE32C_PREFLIGHT_QUERY
mode: content
max_results: 3
REASON: bounded plain-text compatibility probe.
""", None

    def get_stats(self):
        return {
            "last_http_status": self.last_http_status,
            "last_error_category": self.last_error_category,
            "last_error_codes": list(self.last_error_codes),
            "last_request_id": self.last_request_id,
            "http_attempts": len(self.calls),
        }


def test_qwen_preflight_passes_when_native_mode_fails_but_text_mode_works():
    provider = _PreflightFallbackProvider()

    def builder(config, budget, provider_name, model_name, environ=None):
        return provider

    report = run_preflight(
        "cloudflare",
        MODEL,
        environ={},
        provider_builder=builder,
    )

    assert report["transport_probe"]["status"] == "completed"
    assert report["native_tool_call_probe"]["status"] == "provider_failed"
    assert report["text_response_probe"]["status"] == "passed"
    assert report["text_response_probe"]["normalization_strategy"] == "labelled_text"
    assert report["text_response_probe"]["tool_executed"] is False
    assert report["response_mode_status"] == "text_fallback_only"
    assert report["usable_response_modes"] == ["plain_text_envelope"]
    assert report["status"] == "passed"
    assert provider.calls == ["transport", "native", "text"]


def test_text_fallback_is_limited_to_non_transient_request_rejections():
    class StatsProvider:
        def __init__(self, status, category):
            self.status = status
            self.category = category

        def get_stats(self):
            return {
                "last_http_status": self.status,
                "last_error_category": self.category,
            }

    assert should_fallback_to_plain_text(StatsProvider(400, "provider_request_rejected"))
    assert should_fallback_to_plain_text(StatsProvider(422, "request_schema_rejected"))
    assert not should_fallback_to_plain_text(StatsProvider(401, "permission_denied"))
    assert not should_fallback_to_plain_text(StatsProvider(429, "rate_limited"))
    assert not should_fallback_to_plain_text(StatsProvider(503, "provider_internal_error"))
