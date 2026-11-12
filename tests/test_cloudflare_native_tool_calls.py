import json

from providers.base import ProviderToolCall
from providers.cloudflare import CloudflareProvider
from audit_engine.semantic_audit.ae32c.response_protocol import (
    RESPONSE_TOOL_NAME,
    build_response_tool_definition,
)


MODEL = "@cf/qwen/qwen3.8-27b"


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
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


def test_qwen_native_tool_call_uses_openai_schema_and_named_tool_choice_on_ai_run(monkeypatch):
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
    assert kwargs["json"]["tools"] == [build_response_tool_definition()]
    assert kwargs["json"]["tool_choice"] == {
        "type": "function",
        "function": {"name": RESPONSE_TOOL_NAME},
    }
    assert kwargs["json"]["parallel_tool_calls"] is False
    assert kwargs["json"]["max_completion_tokens"] == 256
    assert "max_tokens" not in kwargs["json"]
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


def test_qwen_native_tool_call_parses_openai_style_choices_response(monkeypatch):
    calls = []
    response = FakeResponse({
        "id": "chatcmpl-test",
        "choices": [{
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call-test",
                    "type": "function",
                    "function": {
                        "name": RESPONSE_TOOL_NAME,
                        "arguments": json.dumps(_call_arguments()),
                    },
                }],
            },
        }],
        "usage": {"prompt_tokens": 31, "completion_tokens": 19, "total_tokens": 50},
    })
    monkeypatch.setattr(
        "providers.cloudflare.requests.post",
        lambda url, **kwargs: (calls.append((url, kwargs)) or response),
    )
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "private-secret-value", [MODEL])
    result, error = provider.chat_with_response_tool(
        [{"role": "user", "content": "Submit the dry-run response."}],
        tool_definition=build_response_tool_definition(),
        temperature=0.0,
        max_tokens=256,
        model=MODEL,
    )
    assert error is None
    assert isinstance(result, ProviderToolCall)
    assert result.name == RESPONSE_TOOL_NAME
    assert result.arguments == _call_arguments()
    assert provider.get_stats()["last_finish_reason"] == "tool_calls"
    assert response.closed


def test_native_tool_http_error_exposes_only_safe_cloudflare_diagnostics(monkeypatch):
    secret_fragment = "Bearer do-not-leak-this"
    response = FakeResponse(
        {
            "success": False,
            "errors": [{
                "code": 12345,
                "message": f"Invalid function tool schema: {secret_fragment}",
            }],
        },
        status_code=400,
        headers={"cf-ray": "a1b2c3d4e5f67890"},
    )
    monkeypatch.setattr("providers.cloudflare.requests.post", lambda *a, **k: response)
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "private-secret-value", [MODEL])
    result, error = provider.chat_with_response_tool(
        [{"role": "user", "content": "probe"}],
        tool_definition=build_response_tool_definition(),
        model=MODEL,
    )
    stats = provider.get_stats()
    assert result is None
    assert "HTTP 400" in error
    assert "request_schema_rejected" in error
    assert "12345" in error
    assert "a1b2c3d4e5f67890" in error
    assert secret_fragment not in error
    assert secret_fragment not in repr(stats)
    assert stats["native_tool_call_failures"] == 1
    assert stats["last_http_status"] == 400
    assert stats["last_error_category"] == "request_schema_rejected"
    assert stats["last_error_codes"] == [12345]
    assert stats["last_request_id"] == "a1b2c3d4e5f67890"
    assert stats["last_endpoint_mode"] == "workers_ai_run_named_function_tool"
    assert response.closed


def test_native_tool_request_rejects_legacy_flat_definition(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "providers.cloudflare.requests.post",
        lambda *a, **k: calls.append(1),
    )
    provider = CloudflareProvider("account", "token", [MODEL])
    result, error = provider.chat_with_response_tool(
        [{"role": "user", "content": "probe"}],
        tool_definition={
            "name": RESPONSE_TOOL_NAME,
            "description": "legacy",
            "parameters": {"type": "object", "properties": {}},
        },
        model=MODEL,
    )
    assert result is None
    assert error == "Invalid response-tool definition"
    assert calls == []

