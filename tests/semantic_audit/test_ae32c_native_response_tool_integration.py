from __future__ import annotations

import json

from providers.base import ProviderToolCall
from audit_engine.semantic_audit.ae32c.response_protocol import (
    RESPONSE_TOOL_NAME,
    build_response_tool_definition,
)
from tests.semantic_audit.test_ae32c_investigator import (
    FakeEvidenceTools,
    FakeProvider,
    SOURCE,
    SOURCE_HASH,
    action_tool,
    final_action,
)
from audit_engine.semantic_audit.ae32c import InvestigationLimits, RepositoryInvestigator


MODEL = "@cf/qwen/qwen3.8-27b"


def _wrap_action(canonical_json: str) -> ProviderToolCall:
    canonical = json.loads(canonical_json)
    if canonical["action"] == "tool_call":
        arguments = {
            "action": "tool_call",
            "tool": canonical["tool"],
            "arguments": canonical["arguments"],
            "reason": canonical["reason"],
            "diagnosis": {},
        }
    else:
        arguments = {
            "action": "final",
            "tool": "",
            "arguments": {},
            "reason": "",
            "diagnosis": canonical["diagnosis"],
        }
    return ProviderToolCall(RESPONSE_TOOL_NAME, arguments)


class NativeCloudflareFakeProvider(FakeProvider):
    provider_name = "cloudflare"
    model = MODEL

    def __init__(self, responses):
        super().__init__(responses)
        self.native_tool_definitions = []
        self.structured_calls = 0

    def get_capabilities(self):
        return {
            "json_object_mode": False,
            "json_schema_mode": False,
            "native_tool_calls": True,
            "plain_text_mode": True,
            "finish_reason_reporting": False,
        }

    def chat_structured(self, messages, temperature=0.2, max_tokens=None, model=None):
        self.structured_calls += 1
        return self.chat(messages, temperature=temperature, max_tokens=max_tokens, model=model)

    def chat_with_response_tool(
        self, messages, *, tool_definition, temperature=0.2, max_tokens=None, model=None
    ):
        self.native_tool_definitions.append(tool_definition)
        return self.chat(messages, temperature=temperature, max_tokens=max_tokens, model=model)


def _make_native_investigator(responses, *, max_rounds=3, finalization_rounds_reserved=1):
    provider = NativeCloudflareFakeProvider(responses)
    evidence = FakeEvidenceTools()
    investigator = RepositoryInvestigator(
        ".",
        provider,
        provider_name="cloudflare",
        model_name=MODEL,
        evidence_tools=evidence,
        limits=InvestigationLimits(
            max_rounds=max_rounds,
            finalization_rounds_reserved=finalization_rounds_reserved,
        ),
        id_factory=lambda: "native-response-tool-test",
    )
    return investigator, provider, evidence


def test_investigator_uses_native_response_tool_and_keeps_existing_action_validation():
    responses = [
        _wrap_action(action_tool(
            "search_repository",
            {"query": "observed", "mode": "content", "max_results": 5},
        )),
        _wrap_action(final_action(evidence_id="E0002", source_reference=True)),
    ]
    investigator, provider, evidence = _make_native_investigator(responses)

    report = investigator.run("Investigate the provider interface mismatch.")

    assert report["status"] == "completed_with_incomplete_evidence"
    assert [tool for tool, _ in evidence.calls] == ["repository_summary", "search_repository"]
    assert len(provider.native_tool_definitions) == 2
    assert all(
        definition["function"]["name"] == RESPONSE_TOOL_NAME
        for definition in provider.native_tool_definitions
    )
    assert provider.structured_calls == 0
    native_events = [
        event for event in report["errors"]
        if event.get("event") == "provider_native_tool_call_requested"
    ]
    assert len(native_events) == 2
    normalized_events = [
        event for event in report["errors"]
        if event.get("event") == "provider_response_normalized"
        and event.get("strategy") == "native_tool_call"
    ]
    assert len(normalized_events) == 2
    assert any(
        "Response-channel instruction" in message.get("content", "")
        for message in provider.messages[0]
    )


def test_native_response_tool_does_not_bypass_finalization_no_tool_rule():
    first = _wrap_action(action_tool(
        "search_repository",
        {"query": "observed", "mode": "content", "max_results": 5},
    ))
    forbidden_finalization_tool = _wrap_action(action_tool(
        "search_repository",
        {"query": "second", "mode": "content", "max_results": 5},
    ))
    investigator, provider, evidence = _make_native_investigator(
        [first, forbidden_finalization_tool],
        max_rounds=2,
        finalization_rounds_reserved=1,
    )

    report = investigator.run("Investigate the provider interface mismatch.")

    assert [tool for tool, _ in evidence.calls] == ["repository_summary", "search_repository"]
    rejected = [
        event for event in report["errors"]
        if event.get("event") == "finalization_tool_request_rejected"
    ]
    assert rejected
    assert rejected[0]["tool_dispatched"] is False
    assert report["budget"]["finalization_tool_requests_rejected"] == 1


def test_malformed_native_arguments_are_recoverable_model_rejections_not_provider_failures():
    malformed = (
        '{"action":"tool_call","action":"final","tool":"repository_summary",'
        '"arguments":{},"reason":"x","diagnosis":{}}'
    )
    provider = NativeCloudflareFakeProvider([
        ProviderToolCall(RESPONSE_TOOL_NAME, malformed),
        action_tool(
            "search_repository",
            {"query": "observed", "mode": "content", "max_results": 5},
        ),
        final_action(evidence_id="E0002", source_reference=True),
    ])
    evidence = FakeEvidenceTools()
    investigator = RepositoryInvestigator(
        ".",
        provider,
        provider_name="cloudflare",
        model_name=MODEL,
        evidence_tools=evidence,
        limits=InvestigationLimits(
            max_rounds=3,
            finalization_rounds_reserved=1,
            max_invalid_json_retries=1,
            max_finalization_invalid_json_retries=1,
        ),
        id_factory=lambda: "native-malformed-recovery-test",
    )

    report = investigator.run("Investigate the provider interface mismatch.")

    assert report["diagnosis"] is not None
    assert investigator._response_mode_override == "plain_text"
    assert [tool for tool, _ in evidence.calls] == ["repository_summary", "search_repository"]
    assert any(
        event.get("event") == "model_action_rejected"
        and event.get("parse_error_code") == "duplicate_json_key"
        for event in report["errors"]
    )
    assert any(
        event.get("event") == "provider_response_contract_downgrade_requested"
        and event.get("to_mode") == "plain_text"
        for event in report["errors"]
    )
    assert not any(event.get("event") == "provider_failure" for event in report["errors"])

