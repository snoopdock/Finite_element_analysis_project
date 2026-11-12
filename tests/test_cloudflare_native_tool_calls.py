from providers.base import ProviderToolCall
from providers.cloudflare import CloudflareProvider
from audit_engine.semantic_audit.ae32c.response_protocol import (
    RESPONSE_TOOL_NAME,
    build_response_tool_definition,
)


MODEL = "@cf/qwen/qwen3.8-27b"


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.closed = False

    def json(self):
        return self._payload

    def close(self):
        self.closed = True


def _call_arguments():
    return {
        "action": "tool_call",
        "tool": "repository_summary",
        "arguments": {},
        "reason": "Check the repository evidence index.",
        "diagnosis": {},
    }


def test_qwen_adapter_declares_native_tool_support_only_for_single_exact_model():
    qwen = CloudflareProvider("account", "private-secret-value", [MODEL])
    other = CloudflareProvider("account", "token", ["@cf/meta/llama-3.1-8b-instruct-fast"])
    mixed = CloudflareProvider("account", "token", [MODEL, "@cf/meta/llama-3.1-8b-instruct-fast"])

    assert qwen.get_capabilities()["native_tool_calls"] is True
    assert qwen.get_capabilities()["json_object_mode"] is False
    assert other.get_capabilities()["native_tool_calls"] is False
    assert mixed.get_capabilities()["native_tool_calls"] is False


def test_qwen_native_tool_call_uses_documented_ai_run_tools_shape(monkeypatch):
    calls = []
    response = FakeResponse({
        "success": True,
        "result": {
            "response": "",
            "tool_calls": [{
                "name": RESPONSE_TOOL_NAME,
                "arguments": _call_arguments(),
            }],
            "usage": {"prompt_tokens": 30, "completion_tokens": 20, "total_tokens": 50},
        },
    })
    monkeypatch.setattr(
        "providers.cloudflare.requests.post",
        lambda url, **kwargs: (calls.append((url, kwargs)) or response),
    )
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "private-secret-value", [MODEL], max_logical_calls=2)

    result, error = provider.chat_with_response_tool(
        [{"role": "system", "content": "Use the response function."}],
        tool_definition=build_response_tool_definition(),
        temperature=0.0,
        max_tokens=256,
        model=MODEL,
    )

    assert error is None
    assert isinstance(result, ProviderToolCall)
    assert result.name == RESPONSE_TOOL_NAME
    assert result.arguments == _call_arguments()
    url, kwargs = calls[0]
    assert url.endswith("/ai/run/" + MODEL)
    assert kwargs["json"]["tools"] == [{
        "name": RESPONSE_TOOL_NAME,
        "description": build_response_tool_definition()["function"]["description"],
        "parameters": build_response_tool_definition()["function"]["parameters"],
    }]
    assert "response_format" not in kwargs["json"]
    assert response.closed
    stats = provider.get_stats()
    assert stats["native_tool_call_requests"] == 1
    assert stats["native_tool_call_responses"] == 1
    assert stats["successful_calls"] == 1
    assert stats["usage"]["total_tokens"] == 50
    assert "private-secret-value" not in repr(stats)


def test_qwen_native_tool_call_rejects_multiple_calls_before_returning(monkeypatch):
    response = FakeResponse({
        "success": True,
        "result": {
            "tool_calls": [
                {"name": RESPONSE_TOOL_NAME, "arguments": _call_arguments()},
                {"name": RESPONSE_TOOL_NAME, "arguments": _call_arguments()},
            ]
        },
    })
    monkeypatch.setattr("providers.cloudflare.requests.post", lambda *a, **k: response)
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "private-secret-value", [MODEL])
    result, error = provider.chat_with_response_tool(
        [{"role": "user", "content": "probe"}],
        tool_definition=build_response_tool_definition(),
        model=MODEL,
    )
    assert result is None
    assert error == "Native response-tool call count invalid"
    assert provider.get_stats()["native_tool_call_failures"] == 1


def test_qwen_native_tool_call_rejects_duplicate_keys_in_string_arguments(monkeypatch):
    raw = '{"action":"tool_call","action":"final","tool":"repository_summary","arguments":{},"reason":"x","diagnosis":{}}'
    response = FakeResponse({
        "success": True,
        "result": {
            "tool_calls": [{"name": RESPONSE_TOOL_NAME, "arguments": raw}]
        },
    })
    monkeypatch.setattr("providers.cloudflare.requests.post", lambda *a, **k: response)
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "private-secret-value", [MODEL])
    result, error = provider.chat_with_response_tool(
        [{"role": "user", "content": "probe"}],
        tool_definition=build_response_tool_definition(),
        model=MODEL,
    )
    assert result is None
    assert error == "Native response-tool arguments invalid"
    assert raw not in repr(provider.get_stats())


def test_qwen_native_tool_call_can_fall_back_to_text_for_normalizer(monkeypatch):
    response = FakeResponse({
        "success": True,
        "result": {"response": "ACTION: tool_call\\nTOOL: repository_summary\\nARGUMENTS: {}\\nREASON: inspect", "tool_calls": []},
    })
    monkeypatch.setattr("providers.cloudflare.requests.post", lambda *a, **k: response)
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "private-secret-value", [MODEL])
    result, error = provider.chat_with_response_tool(
        [{"role": "user", "content": "probe"}],
        tool_definition=build_response_tool_definition(),
        model=MODEL,
    )
    assert error is None
    assert isinstance(result, str)
    assert result.startswith("ACTION:")



def test_cloudflare_json_object_capability_is_model_scoped_to_published_allowlist():
    supported = CloudflareProvider(
        "account", "private-secret-value", ["@cf/meta/llama-3.1-8b-instruct"]
    )
    unsupported = CloudflareProvider(
        "account", "private-secret-value", ["@cf/meta/llama-3.1-8b-instruct-fast"]
    )
    assert supported.get_capabilities()["json_object_mode"] is True
    assert unsupported.get_capabilities()["json_object_mode"] is False



def test_native_response_tool_method_fails_closed_for_other_cloudflare_models(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "providers.cloudflare.requests.post",
        lambda *a, **k: calls.append(1),
    )
    provider = CloudflareProvider(
        "account", "private-secret-value", ["@cf/meta/llama-3.1-8b-instruct"]
    )
    result, error = provider.chat_with_response_tool(
        [{"role": "user", "content": "probe"}],
        tool_definition=build_response_tool_definition(),
        model="@cf/meta/llama-3.1-8b-instruct",
    )
    assert result is None
    assert error == "Native response-tool mode is not enabled for this model"
    assert calls == []
