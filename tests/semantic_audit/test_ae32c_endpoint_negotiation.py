"""Deterministic, network-free cross-provider endpoint negotiation contracts."""
from __future__ import annotations

import json
import pytest

from providers.base import ProviderResponse, ProviderToolCall
from providers.capabilities import should_fallback_to_plain_text
from providers.openai_compatible import OpenAICompatibleProvider
from providers.response_negotiation import (
    OpenRouterCapabilityCache, parse_openrouter_endpoints, select_response_mode,
)
from audit_engine.semantic_audit.ae32c.response_protocol import (
    RESPONSE_TOOL_NAME, build_portable_wire_schema,
)
from audit_engine.semantic_audit.ae32c.response_normalizer import (
    normalize_provider_response, ResponseNormalizationError,
)
from audit_engine.semantic_audit.ae32c import InvestigationLimits, RepositoryInvestigator
from tests.semantic_audit.test_ae32c_investigator import (
    FakeProvider, FakeEvidenceTools, action_tool, final_action,
)


MODEL = "nvidia/nemotron-3.5-lightning:free"
ACTION = {"action": "tool_call", "tool": "repository_summary", "arguments": {}, "reason": "inspect"}


class FakeHTTPResponse:
    def __init__(self, data, code=200):
        self.data = data
        self.status_code = code
        self.headers = {}
        self.closed = False
    def json(self):
        return self.data
    def close(self):
        self.closed = True


def _metadata(*parameter_lists):
    return {"data": {"id": MODEL, "endpoints": [
        {"name": f"endpoint-{i}", "supported_parameters": params}
        for i, params in enumerate(parameter_lists)
    ]}}


def test_endpoint_capability_selection_is_not_model_level_union():
    caps = parse_openrouter_endpoints(_metadata(["tools"], ["response_format"]), MODEL)
    assert caps.endpoint_count == 2
    assert not caps.json_schema
    assert caps.native_tools and caps.json_object
    assert caps.select_mode() == "native_tool_call"
    caps = parse_openrouter_endpoints(_metadata(["structured_outputs", "response_format"]), MODEL)
    assert caps.json_schema
    assert caps.select_mode() == "json_schema"
    assert select_response_mode(json_schema=False, native_tool_calls=False, json_object=False) == "plain_text"


@pytest.mark.parametrize("payload", [
    {}, {"data": {"id": "unrelated/model", "endpoints": [{"supported_parameters": ["tools"]}]}},
    {"data": {"id": MODEL, "endpoints": {"x": []}}},
    {"data": {"id": MODEL, "endpoints": [{"supported_parameters": "tools"}]}},
])
def test_invalid_endpoint_metadata_fails_closed(payload):
    assert parse_openrouter_endpoints(payload, MODEL).select_mode() == "plain_text"


def test_capability_cache_is_bounded_keyed_and_expires_without_leaking_api_key():
    now = [100.0]
    cache = OpenRouterCapabilityCache(ttl_seconds=60, clock=lambda: now[0])
    calls = []
    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeHTTPResponse(_metadata(["tools"]))
    first = cache.get(model=MODEL, api_key="sensitive-token", request_get=fake_get)
    assert first.native_tools
    assert len(calls) == 1
    assert calls[0][0] == f"https://openrouter.ai/api/v1/models/nvidia/nemotron-3.5-lightning%3Afree/endpoints"
    assert calls[0][1]["stream"] is True
    assert calls[0][1]["allow_redirects"] is False
    assert cache.get(model=MODEL, api_key="sensitive-token", request_get=fake_get) == first
    assert len(calls) == 1
    now[0] += 60.1
    cache.get(model=MODEL, api_key="sensitive-token", request_get=fake_get)
    assert len(calls) == 2
    assert "sensitive-token" not in repr(cache._values)
    assert cache.get(model="not/a/valid/model", api_key="token", request_get=fake_get).source == "invalid_model_identifier"
    assert len(calls) == 2


def test_metadata_transport_failure_does_not_guess_capabilities():
    cache = OpenRouterCapabilityCache()
    r = cache.get(model=MODEL, api_key="secret", request_get=lambda *a, **k: FakeHTTPResponse({}, code=503))
    assert r.select_mode() == "plain_text"
    assert r.source == "metadata_http_failure"


def test_portable_wire_schema_requires_one_serialized_action_only():
    schema = build_portable_wire_schema()
    assert schema["additionalProperties"] is False
    assert schema["required"] == list(schema["properties"])
    assert schema["properties"]["action_json"]["type"] == "string"
    encoded = json.dumps({"action_json": json.dumps(ACTION)})
    out = normalize_provider_response(encoded)
    assert out.strategy == "portable_wire_json"
    assert out.payload == ACTION
    call = ProviderToolCall(RESPONSE_TOOL_NAME, {"action_json": json.dumps(ACTION)})
    assert normalize_provider_response(ProviderResponse(tool_calls=(call,))).strategy == "native_portable_wire"
    with pytest.raises(ResponseNormalizationError) as exc:
        normalize_provider_response('{"action_json":"{\\"action\\":1,\\"action\\":2}"}')
    assert exc.value.code in {"json_syntax_error", "duplicate_json_key"}
    with pytest.raises(ResponseNormalizationError):
        normalize_provider_response(ProviderToolCall("write_repo", {"action_json": json.dumps(ACTION)}))


def test_openrouter_strict_schema_request_and_optional_healing(monkeypatch):
    monkeypatch.setenv("FEA_OPENROUTER_CAPABILITY_DISCOVERY", "1")
    monkeypatch.setenv("FEA_OPENROUTER_RESPONSE_HEALING", "1")
    import providers.response_negotiation as discovery
    import providers.openai_compatible as adapter
    captured = []
    monkeypatch.setattr(discovery.requests, "get", lambda *a, **k: FakeHTTPResponse(_metadata(["structured_outputs", "tools"])))
    def fake_post(url, **kwargs):
        captured.append(kwargs["json"])
        return FakeHTTPResponse({
            "model": MODEL,
            "choices": [{"message": {"content": json.dumps({"action_json": json.dumps(ACTION)})}, "finish_reason": "stop"}],
        })
    monkeypatch.setattr(adapter.requests, "post", fake_post)
    p = OpenAICompatibleProvider("openrouter", "secret-token", MODEL, max_retries=1)
    response, error = p.chat_negotiated([{"role": "user", "content": "test"}])
    assert error is None
    assert normalize_provider_response(response).payload == ACTION
    data = captured[0]
    assert data["response_format"]["type"] == "json_schema"
    assert data["response_format"]["json_schema"]["strict"] is True
    assert data["provider"] == {"require_parameters": True}
    assert data["plugins"] == [{"id": "response-healing"}]
    assert p.get_stats()["response_strategy"] == "json_schema"
    assert "secret-token" not in repr(p.get_stats())


def test_openrouter_tool_call_is_inert_and_untrusted(monkeypatch):
    monkeypatch.setenv("FEA_OPENROUTER_CAPABILITY_DISCOVERY", "1")
    import providers.response_negotiation as discovery
    import providers.openai_compatible as adapter
    monkeypatch.setattr(discovery.requests, "get", lambda *a, **k: FakeHTTPResponse(_metadata(["tools"])))
    seen = []
    def fake_post(url, **kwargs):
        seen.append(kwargs["json"])
        return FakeHTTPResponse({
            "choices": [{"message": {"content": None, "tool_calls": [
                {"type": "function", "function": {"name": RESPONSE_TOOL_NAME, "arguments": json.dumps({"action_json": json.dumps(ACTION)})}}
            ]}, "finish_reason": "tool_calls"}],
        })
    monkeypatch.setattr(adapter.requests, "post", fake_post)
    p = OpenAICompatibleProvider("openrouter", "secret-token", MODEL)
    response, error = p.chat_negotiated([{"role": "user", "content": "test"}])
    assert error is None
    assert isinstance(response, ProviderResponse)
    assert normalize_provider_response(response).payload == ACTION
    assert seen[0]["tool_choice"] == "auto"
    assert seen[0]["provider"] == {"require_parameters": True}
    assert "response_format" not in seen[0]
    assert "plugins" not in seen[0]


def test_discovery_off_does_not_make_metadata_request(monkeypatch):
    monkeypatch.delenv("FEA_OPENROUTER_CAPABILITY_DISCOVERY", raising=False)
    import providers.openai_compatible as adapter
    monkeypatch.setattr(adapter.requests, "post", lambda *a, **k: FakeHTTPResponse({
        "choices": [{"message": {"content": json.dumps(ACTION)}, "finish_reason": "stop"}],
    }))
    p = OpenAICompatibleProvider("openrouter", "secret", MODEL)
    out, err = p.chat_negotiated([{"role": "user", "content": "go"}])
    assert err is None and out == json.dumps(ACTION)
    assert p.get_stats()["response_strategy"] == "plain_text"
    assert p.get_stats()["endpoint_capability_source"] == "not_queried"


class _NegotiatedRejectingProvider(FakeProvider):
    provider_name = "openrouter"
    model = MODEL
    supports_negotiated_responses = True
    def __init__(self, responses):
        super().__init__(responses)
        self.fallbacks = 0
        self.last_http_status = 404
        self.response_strategy = "json_schema"
        self.error_category = "required_parameters_no_endpoint"
    def chat_negotiated(self, messages, **kwargs):
        self.http_attempts += 1
        return None, "openrouter HTTP 404"
    def chat_text(self, messages, **kwargs):
        self.fallbacks += 1
        return self.chat(messages, **kwargs)
    def get_stats(self):
        out = super().get_stats()
        out.update({"last_http_status": self.last_http_status, "response_strategy": self.response_strategy,
                    "last_http_error_diagnostic": {"http_status": self.last_http_status,
                                                   "error_message_category": self.error_category}})
        return out


def test_negotiated_404_required_parameters_rejection_falls_back_with_reservation():
    provider = _NegotiatedRejectingProvider([
        action_tool("search_repository", {"query": "observed", "mode": "content", "max_results": 5}),
        final_action(),
    ])
    evidence = FakeEvidenceTools()
    investigator = RepositoryInvestigator(".", provider, provider_name="openrouter", model_name=MODEL,
        evidence_tools=evidence, limits=InvestigationLimits(max_rounds=2, finalization_rounds_reserved=1),
        id_factory=lambda: "endpoint-negotiation-test")
    report = investigator.run("Find the interface problem.")
    assert provider.fallbacks == 2
    assert report["status"] == "completed_with_incomplete_evidence"
    assert any(e.get("event") == "provider_response_strategy_selected" for e in report["errors"])
    assert len([e for e in report["errors"] if e.get("event") == "provider_response_mode_fallback_completed"]) == 1
    mode_summary = report["interaction_diagnostics"]["response_mode_negotiation"]
    assert mode_summary["initial_mode"] == "json_schema"
    assert mode_summary["session_override"] == "plain_text"
    assert mode_summary["plain_text_downgrade_used"] is True


def test_unclassified_or_model_not_found_404_does_not_fallback():
    class Provider:
        def __init__(self, category): self.category = category
        def get_stats(self):
            return {"last_http_status": 404, "response_strategy": "json_schema", "last_http_error_diagnostic": {
                "http_status": 404, "error_message_category": self.category}}
    assert should_fallback_to_plain_text(Provider("required_parameters_no_endpoint"))
    assert not should_fallback_to_plain_text(Provider("model_identifier_rejected"))
    assert not should_fallback_to_plain_text(Provider("other_unclassified"))


def test_openrouter_preflight_uses_negotiated_probe_without_repository_tool_dispatch():
    from audit_engine.semantic_audit.ae32c.provider_preflight import run_preflight
    class FakeOpenRouter:
        provider_name = "openrouter"
        model = MODEL
        supports_negotiated_responses = True
        def __init__(self): self.probe_calls = []
        def chat(self, messages, **kw):
            self.probe_calls.append("transport")
            return "AE32C_PREFLIGHT_OK", None
        def chat_negotiated(self, messages, **kw):
            self.probe_calls.append("negotiated")
            return ProviderResponse(text=json.dumps({"action_json": json.dumps(ACTION)})), None
        def chat_text(self, messages, **kw):
            self.probe_calls.append("text")
            return ("ACTION: tool_call\nTOOL: search_repository\nARGUMENTS:\n"
                    "query: AE32C_PREFLIGHT_QUERY\nmode: content\nmax_results: 3\n"
                    "REASON: inspect\n"), None
        def get_stats(self):
            return {"response_strategy": "json_schema", "endpoint_capability_source": "fixture_endpoint",
                    "endpoint_capability_count": 1}
    provider = FakeOpenRouter()
    def builder(config, budget, provider_name, model_name, environ=None):
        return provider
    result = run_preflight("openrouter", MODEL, environ={}, provider_builder=builder)
    assert result["status"] == "passed"
    assert result["negotiated_response_probe"]["status"] == "passed"
    assert result["negotiated_response_probe"]["tool_executed"] is False
    assert result["usable_response_modes"] == ["negotiated_response", "plain_text_envelope"]
    assert provider.probe_calls == ["transport", "negotiated", "text"]


def test_openrouter_404_classifier_requires_explicit_parameter_routing_rejection():
    from providers.openai_compatible import http_error_diagnostic
    routed = http_error_diagnostic({"error": {"message": "No endpoints found supporting the requested parameters."}}, 404)
    assert routed["error_message_category"] == "required_parameters_no_endpoint"
    missing_model = http_error_diagnostic({"error": {"message": "Unknown model deployment"}}, 404)
    assert missing_model["error_message_category"] == "model_identifier_rejected"
    assert should_fallback_to_plain_text(type("P", (), {"get_stats": lambda self: {
        "response_strategy": "json_schema", "last_http_status": 404, "last_http_error_diagnostic": routed
    }})())
    assert not should_fallback_to_plain_text(type("P", (), {"get_stats": lambda self: {
        "response_strategy": "json_schema", "last_http_status": 404, "last_http_error_diagnostic": missing_model
    }})())


def test_metadata_redirect_does_not_follow_or_leak_credentials():
    cache = OpenRouterCapabilityCache()
    calls = []
    def get(url, **kw):
        calls.append((url, kw))
        return FakeHTTPResponse({}, code=302)
    out = cache.get(model=MODEL, api_key="top-secret", request_get=get)
    assert out.select_mode() == "plain_text"
    assert calls[0][1]["allow_redirects"] is False
    assert "top-secret" not in repr(cache._values)


def test_native_calls_with_wrong_function_or_ambiguous_content_fail_closed(monkeypatch):
    from providers import response_negotiation as disc, openai_compatible as adapter
    monkeypatch.setenv("FEA_OPENROUTER_CAPABILITY_DISCOVERY", "1")
    monkeypatch.setattr(disc.requests, "get", lambda *a, **k: FakeHTTPResponse(_metadata(["tools"])))
    def post(url, **kw):
        return FakeHTTPResponse({"choices": [{"message": {"content": "", "tool_calls": [{
            "function": {"name": "run_shell", "arguments": json.dumps({"action_json": json.dumps(ACTION)})}
        }]}, "finish_reason": "tool_calls"}]})
    monkeypatch.setattr(adapter.requests, "post", post)
    provider = OpenAICompatibleProvider("openrouter", "secret", MODEL)
    response, err = provider.chat_negotiated([{"role": "user", "content": "test"}])
    assert err is None
    with pytest.raises(ResponseNormalizationError) as exc:
        normalize_provider_response(response)
    assert exc.value.code == "unexpected_native_tool_name"
