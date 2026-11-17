import hashlib
import json

import requests
import pytest

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


def test_qwen_native_tool_call_uses_openai_compatible_chat_completions_contract(monkeypatch):
    calls = []
    response = FakeResponse({
        "id": "chatcmpl-native-test",
        "choices": [{
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call-native-test",
                    "type": "function",
                    "function": {
                        "name": RESPONSE_TOOL_NAME,
                        "arguments": json.dumps(_call_arguments()),
                    },
                }],
            },
        }],
        "usage": {"prompt_tokens": 30, "completion_tokens": 20, "total_tokens": 50},
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
        max_tokens=2048,
        model=MODEL,
    )

    assert error is None
    assert isinstance(result, ProviderToolCall)
    assert result.name == RESPONSE_TOOL_NAME
    assert result.arguments == _call_arguments()
    url, kwargs = calls[0]
    assert url.endswith("/ai/v1/chat/completions")
    assert kwargs["json"]["model"] == MODEL
    assert kwargs["json"]["messages"] == [
        {"role": "system", "content": "Use the response function."}
    ]
    assert kwargs["json"]["tools"] == [build_response_tool_definition()]
    assert kwargs["json"]["tool_choice"] == "auto"
    assert kwargs["json"]["parallel_tool_calls"] is False
    assert kwargs["json"]["max_completion_tokens"] == 2048
    assert kwargs["json"]["stream"] is False
    assert "max_tokens" not in kwargs["json"]
    assert "response_format" not in kwargs["json"]
    assert response.closed
    stats = provider.get_stats()
    assert stats["native_tool_call_requests"] == 1
    assert stats["native_tool_call_responses"] == 1
    assert stats["successful_calls"] == 1
    assert stats["usage"]["total_tokens"] == 50
    assert "private-secret-value" not in repr(stats)


def test_qwen_openai_compatible_transport_probe_uses_chat_completions_endpoint(monkeypatch):
    calls = []
    response = FakeResponse({
        "id": "chatcmpl-transport-test",
        "choices": [{
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": "AE32C_PREFLIGHT_OK"},
        }],
        "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
    })
    monkeypatch.setattr(
        "providers.cloudflare.requests.post",
        lambda url, **kwargs: (calls.append((url, kwargs)) or response),
    )
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "private-secret-value", [MODEL])

    text, error = provider.chat_openai_compatible(
        [{"role": "user", "content": "Reply exactly AE32C_PREFLIGHT_OK"}],
        temperature=0.0,
        max_tokens=128,
        model=MODEL,
    )

    assert error is None
    assert text == "AE32C_PREFLIGHT_OK"
    url, kwargs = calls[0]
    assert url.endswith("/ai/v1/chat/completions")
    assert kwargs["json"]["model"] == MODEL
    assert kwargs["json"]["max_completion_tokens"] == 128
    assert kwargs["json"]["stream"] is False
    assert "max_tokens" not in kwargs["json"]
    assert "tools" not in kwargs["json"]
    assert provider.get_stats()["last_endpoint_mode"] == "workers_ai_openai_compatible_chat_completions"


def test_ordinary_cloudflare_chat_keeps_workers_ai_run_contract(monkeypatch):
    calls = []
    response = FakeResponse({
        "success": True,
        "result": {"response": "ordinary response"},
    })
    monkeypatch.setattr(
        "providers.cloudflare.requests.post",
        lambda url, **kwargs: (calls.append((url, kwargs)) or response),
    )
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "token", ["@cf/meta/llama-3.1-8b-instruct-fast"])
    text, error = provider.chat(
        [{"role": "user", "content": "hello"}],
        max_tokens=64,
        model="@cf/meta/llama-3.1-8b-instruct-fast",
    )
    assert error is None
    assert text == "ordinary response"
    url, kwargs = calls[0]
    assert url.endswith("/ai/run/@cf/meta/llama-3.1-8b-instruct-fast")
    assert kwargs["json"]["max_tokens"] == 64
    assert "max_completion_tokens" not in kwargs["json"]


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
    assert stats["last_endpoint_mode"] == "workers_ai_openai_compatible_chat_completions_auto_tool_choice"
    assert response.closed


def test_native_tool_openai_error_envelope_exposes_safe_numeric_code(monkeypatch):
    secret_fragment = "Bearer never-log-this"
    response = FakeResponse(
        {
            "error": {
                "message": f"Invalid function tool schema: {secret_fragment}",
                "type": "invalid_request_error",
                "code": 8007,
            }
        },
        status_code=400,
        headers={"cf-ray": "aabbccddeeff0011"},
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
    assert "8007" in error
    assert "aabbccddeeff0011" in error
    assert secret_fragment not in error
    assert secret_fragment not in repr(stats)
    assert stats["last_error_codes"] == [8007]
    assert stats["last_error_category"] == "request_schema_rejected"
    assert stats["last_endpoint_mode"] == "workers_ai_openai_compatible_chat_completions_auto_tool_choice"
    assert response.closed


def test_native_tool_http_8007_without_message_is_not_given_a_guessed_meaning(monkeypatch):
    response = FakeResponse(
        {"success": False, "errors": [{"code": 8007}]},
        status_code=400,
        headers={"cf-ray": "c0ffee1234567890"},
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
    assert "8007" in error
    assert "c0ffee1234567890" in error
    assert stats["last_error_category"] == "provider_request_rejected"
    assert stats["last_error_codes"] == [8007]
    assert response.closed


def test_qwen_native_tool_call_rejects_forced_named_tool_choice(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "providers.cloudflare.requests.post",
        lambda *a, **k: calls.append(1),
    )
    provider = CloudflareProvider("account", "token", [MODEL])
    result, error = provider.chat(
        [{"role": "user", "content": "probe"}],
        model=MODEL,
        tools=[build_response_tool_definition()],
        tool_choice={
            "type": "function",
            "function": {"name": RESPONSE_TOOL_NAME},
        },
        _openai_compatible=True,
    )
    assert result is None
    assert error == "Qwen native response tools require auto tool choice"
    assert calls == []


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




def test_cloudflare_chat_text_uses_plain_openai_compatible_request(monkeypatch):
    calls = []
    response = FakeResponse({
        "id": "chatcmpl-text-fallback",
        "choices": [{
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": "ACTION: tool_call"},
        }],
    })
    monkeypatch.setattr(
        "providers.cloudflare.requests.post",
        lambda url, **kwargs: (calls.append((url, kwargs)) or response),
    )
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "private-secret-value", [MODEL])

    text, error = provider.chat_text(
        [{"role": "user", "content": "Return a labelled action."}],
        temperature=0.0,
        max_tokens=512,
        model=MODEL,
    )

    assert error is None
    assert text == "ACTION: tool_call"
    url, kwargs = calls[0]
    assert url.endswith("/ai/v1/chat/completions")
    assert kwargs["json"]["model"] == MODEL
    assert "tools" not in kwargs["json"]
    assert "tool_choice" not in kwargs["json"]
    assert "response_format" not in kwargs["json"]
    assert kwargs["json"]["stream"] is False
    assert provider.get_stats()["last_endpoint_mode"] == "workers_ai_openai_compatible_chat_completions"


def test_qwen_native_request_coalesces_initial_system_messages_without_reordering(monkeypatch):
    """Regression for the live 400: both failing preflights had two systems."""
    captured = []
    response = FakeResponse({"choices": [{"message": {"role": "assistant", "content": None,
        "tool_calls": [{"function": {"name": RESPONSE_TOOL_NAME,
                                   "arguments": json.dumps(_call_arguments())}}]}}]})
    monkeypatch.setattr("providers.cloudflare.requests.post",
                        lambda url, **kw: captured.append(kw["json"]) or response)
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "secret-do-not-leak", [MODEL])
    messages = [{"role": "system", "content": "Original safety policy."},
                {"role": "system", "content": "Virtual response instruction."},
                {"role": "user", "content": "Read-only response please."}]
    snapshot = [dict(m) for m in messages]
    result, error = provider.chat_with_response_tool(
        messages, tool_definition=build_response_tool_definition(), model=MODEL)
    assert error is None and isinstance(result, ProviderToolCall)
    assert messages == snapshot  # caller context is never modified
    assert captured[0]["messages"] == [
        {"role": "system", "content": "Original safety policy.\n\nVirtual response instruction."},
        {"role": "user", "content": "Read-only response please."},
    ]
    stats = provider.get_stats()
    assert stats["last_system_messages_coalesced"] == 1
    assert stats["last_message_compatibility"] == "qwen_single_initial_system"
    assert "secret-do-not-leak" not in repr(stats)
    assert response.closed


def test_qwen_plain_text_request_coalesces_same_leading_system_sequence(monkeypatch):
    captured = []
    response = FakeResponse({"choices": [{"message": {"role": "assistant", "content":
         "ACTION: tool_call\nTOOL: search_repository\nARGUMENTS:\nquery: AE32C_PREFLIGHT_QUERY\nmode: content\nmax_results: 3\nREASON: read-only check"}}]})
    monkeypatch.setattr("providers.cloudflare.requests.post",
                        lambda url, **kw: captured.append(kw["json"]) or response)
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "token", [MODEL])
    result, error = provider.chat_text([
        {"role": "system", "content": "Plain-text protocol."},
        {"role": "system", "content": "Probe text format."},
        {"role": "user", "content": "Return labelled action."},
    ], model=MODEL, max_tokens=512)
    assert error is None and isinstance(result, str)
    assert captured[0]["messages"][0] == {
        "role": "system", "content": "Plain-text protocol.\n\nProbe text format."}
    assert [m["role"] for m in captured[0]["messages"]] == ["system", "user"]
    assert not {"tools", "tool_choice", "response_format"} & set(captured[0])
    assert provider.get_stats()["last_system_messages_coalesced"] == 1
    assert response.closed


def test_qwen_mid_conversation_system_role_is_rejected_before_http(monkeypatch):
    requests_made = []
    monkeypatch.setattr("providers.cloudflare.requests.post",
                        lambda *a, **kw: requests_made.append(kw) or FakeResponse({}))
    provider = CloudflareProvider("account", "token", [MODEL])
    result, error = provider.chat_text([
        {"role": "system", "content": "Do not change this policy."},
        {"role": "user", "content": "hello"},
        {"role": "system", "content": "Late policy injection"},
    ], model=MODEL)
    assert result is None and "noninitial_system_message" in error
    assert requests_made == []
    stats = provider.get_stats()
    assert stats["http_attempts"] == 0
    assert stats["last_error_category"] == "message_role_sequence_rejected"
    assert stats["last_message_compatibility"] == "rejected"


def test_qwen_system_extension_is_not_silently_discarded(monkeypatch):
    requests_made = []
    monkeypatch.setattr("providers.cloudflare.requests.post",
                        lambda *a, **kw: requests_made.append(kw) or FakeResponse({}))
    provider = CloudflareProvider("account", "token", [MODEL])
    result, error = provider.chat_text([
        {"role": "system", "content": "First"},
        {"role": "system", "content": "Second", "provider_metadata": "security sensitive"},
        {"role": "user", "content": "hello"},
    ], model=MODEL)
    assert result is None and "nonmergeable_system_message" in error
    assert requests_made == []


def test_non_qwen_cloudflare_requests_are_unchanged(monkeypatch):
    captured = []
    response = FakeResponse({"success": True, "result": {"response": "ok"}})
    monkeypatch.setattr("providers.cloudflare.requests.post",
                        lambda url, **kw: captured.append(kw["json"]) or response)
    provider = CloudflareProvider("account", "token", ["@cf/meta/llama-3.1-8b-instruct-fast"])
    messages = [{"role": "system", "content": "One"},
                {"role": "system", "content": "Two"},
                {"role": "user", "content": "Hello"}]
    result, error = provider.chat(messages)
    assert (result, error) == ("ok", None)
    assert captured[0]["messages"] == messages
    assert provider.get_stats()["last_system_messages_coalesced"] == 0


def test_cloudflare_safe_error_classifies_explicit_system_template_error(monkeypatch):
    response = FakeResponse({"errors": [{"code": 8007,
        "message": "System message must be at the beginning. bearer-leak"}]}, 400)
    monkeypatch.setattr("providers.cloudflare.requests.post", lambda *a, **k: response)
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "token", [MODEL])
    output, error = provider.chat_text([{"role": "user", "content": "hello"}], model=MODEL)
    assert output is None
    assert "bearer-leak" not in error
    assert provider.get_stats()["last_error_category"] == "message_role_sequence_rejected"
    # Error code 8007 alone is still not given a guessed meaning.
    assert provider.get_stats()["last_error_codes"] == [8007]
    assert response.closed


def test_portable_message_coalescer_does_not_move_untrusted_later_messages():
    from providers.message_compatibility import (
        coalesce_leading_system_messages, MessageCompatibilityError,
    )
    original = [{"role": "system", "content": "A"},
                {"role": "system", "content": "B"},
                {"role": "user", "content": "C"}]
    folded, count = coalesce_leading_system_messages(original)
    assert count == 1 and folded[0]["content"] == "A\n\nB"
    assert original[0]["content"] == "A"
    try:
        coalesce_leading_system_messages([
            {"role": "user", "content": "C"},
            {"role": "system", "content": "Must not hoist"},
        ])
    except MessageCompatibilityError as exc:
        assert str(exc) == "noninitial_system_message"
    else:
        raise AssertionError("noninitial system instruction was accepted")


def test_live_preflight_shape_single_system_fallback_success_after_native_400(monkeypatch):
    """Offline replay of the three latest live probe outcomes and a fixed text path."""
    from audit_engine.semantic_audit.ae32c.provider_preflight import run_preflight

    replies = [
        FakeResponse({"choices": [{"message": {"role": "assistant", "content":
                     "AE32C_PREFLIGHT_OK"}}]}),
        FakeResponse({"errors": [{"code": 8007}]}, 400),
        FakeResponse({"choices": [{"message": {"role": "assistant", "content":
                     "ACTION: tool_call\nTOOL: search_repository\nARGUMENTS:\n"
                     "query: AE32C_PREFLIGHT_QUERY\nmode: content\nmax_results: 3\n"
                     "REASON: bounded read-only probe"}}]}),
    ]
    requests_seen = []

    def post(url, **kwargs):
        requests_seen.append((url, kwargs["json"]))
        return replies.pop(0)

    monkeypatch.setattr("providers.cloudflare.requests.post", post)
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "private-token", [MODEL], max_logical_calls=3)
    report = run_preflight("cloudflare", MODEL,
                           provider_builder=lambda *a, **k: provider, environ={})
    assert not replies
    assert report["status"] == "passed"
    assert report["transport_probe"]["status"] == "completed"
    assert report["native_tool_call_probe"]["status"] == "provider_failed"
    assert report["text_response_probe"]["status"] == "passed"
    assert report["usable_response_modes"] == ["plain_text_envelope"]
    assert report["response_mode_status"] == "text_fallback_only"
    assert report["text_response_probe"]["system_messages_coalesced"] == 1
    assert report["runtime_settings"]["last_system_messages_coalesced"] == 1
    assert [len([m for m in body["messages"] if m["role"] == "system"])
            for _, body in requests_seen] == [1, 1, 1]
    assert all(url.endswith("/ai/v1/chat/completions") for url, _ in requests_seen)
    assert "tools" not in requests_seen[2][1]
    assert "private-token" not in repr(report)
    assert "bounded read-only probe" not in repr(report)


class FakeStreamResponse(FakeResponse):
    def __init__(self, lines, status_code=200, headers=None):
        super().__init__({}, status_code=status_code, headers=headers or {"Content-Type": "text/event-stream"})
        self._lines = list(lines)

    def iter_lines(self, chunk_size=128, decode_unicode=False):
        self.chunk_size = chunk_size
        for item in self._lines:
            if isinstance(item, (str, bytes)) and (b"\n" in item if isinstance(item, bytes) else "\n" in item or "\r" in item):
                parts = item.splitlines()
                for part in parts:
                    yield part
            else:
                yield item
                # Each legacy fixture item represents one complete SSE event.
                yield b"" if isinstance(item, bytes) else ""

    def iter_content(self, chunk_size=4096, decode_unicode=False):
        self.transport_chunk_size = chunk_size
        for line in self.iter_lines(chunk_size=128, decode_unicode=False):
            value = line if isinstance(line, bytes) else str(line).encode("utf-8")
            yield value + b"\n"


def _sse_event(value):
    return "data: " + json.dumps(value, separators=(",", ":"))


def test_qwen_streaming_text_response_is_normalized_and_reports_latency(monkeypatch):
    calls = []
    response = FakeStreamResponse([
        _sse_event({"choices": [{"index": 0, "delta": {"role": "assistant"}}]}),
        _sse_event({"choices": [{"index": 0, "delta": {"content": "AE32C "}}]}),
        _sse_event({"choices": [{"index": 0, "delta": {"content": "STREAM_OK"}}]}),
        _sse_event({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}),
        "data: [DONE]",
    ])
    monkeypatch.setattr(
        "providers.cloudflare.requests.post",
        lambda url, **kwargs: (calls.append((url, kwargs)) or response),
    )
    monkeypatch.setenv("FEA_LLM_STREAMING", "true")
    monkeypatch.setenv("FEA_LLM_REQUEST_TIMEOUT_SECONDS", "90")
    monkeypatch.setenv("FEA_LLM_CONNECT_TIMEOUT_SECONDS", "10")
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    monkeypatch.setenv("FEA_LLM_REASONING_EFFORT", "medium")
    provider = CloudflareProvider("account", "token", [MODEL])

    text, error = provider.chat_text(
        [{"role": "system", "content": "Reply with a short sentinel."},
         {"role": "user", "content": "Return AE32C STREAM_OK."}],
        temperature=0.0,
        max_tokens=2048,
        model=MODEL,
    )

    assert error is None
    assert text == "AE32C STREAM_OK"
    url, kwargs = calls[0]
    assert url.endswith("/ai/v1/chat/completions")
    assert kwargs["stream"] is True
    assert kwargs["headers"]["Accept"] == "text/event-stream"
    assert kwargs["timeout"] == (10, 90)
    assert kwargs["json"]["stream"] is True
    assert response.chunk_size == 128
    assert response.transport_chunk_size == 4096
    assert kwargs["json"]["reasoning_effort"] == "medium"
    stats = provider.get_stats()
    diag = stats["request_diagnostics"]
    assert diag["streaming"] is True
    assert diag["attempt_count"] == 1
    assert diag["stream_event_count"] == 4
    assert diag["output_chars"] == len("AE32C STREAM_OK")
    assert diag["time_to_first_event_seconds"] is not None
    assert diag["time_to_first_output_seconds"] is not None
    assert diag["max_completion_tokens"] == 2048
    assert diag["reasoning_effort"] == "medium"
    assert response.closed


def test_qwen_streaming_native_tool_call_reassembles_argument_deltas(monkeypatch):
    calls = []
    response = FakeStreamResponse([
        _sse_event({"choices": [{
            "index": 0,
            "delta": {"tool_calls": [{
                "index": 0,
                "id": "call-stream-1",
                "type": "function",
                "function": {
                    "name": RESPONSE_TOOL_NAME,
                    "arguments": '{"action":"tool_call","tool":"repository_summary",',
                },
            }]},
        }]}),
        _sse_event({"choices": [{
            "index": 0,
            "delta": {"tool_calls": [{
                "index": 0,
                "function": {
                    "arguments": '"arguments":{},"reason":"Check the evidence index."}',
                },
            }]},
        }]}),
        _sse_event({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]}),
        "data: [DONE]",
    ])
    monkeypatch.setattr(
        "providers.cloudflare.requests.post",
        lambda url, **kwargs: (calls.append((url, kwargs)) or response),
    )
    monkeypatch.setenv("FEA_LLM_STREAMING", "true")
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "token", [MODEL])

    result, error = provider.chat_with_response_tool(
        [{"role": "system", "content": "Use the response function."},
         {"role": "user", "content": "Inspect the evidence index."}],
        tool_definition=build_response_tool_definition(),
        temperature=0.0,
        max_tokens=2048,
        model=MODEL,
    )

    assert error is None
    assert isinstance(result, ProviderToolCall)
    assert result.name == RESPONSE_TOOL_NAME
    assert result.arguments["action"] == "tool_call"
    assert result.arguments["tool"] == "repository_summary"
    assert result.arguments["reason"] == "Check the evidence index."
    assert calls[0][1]["json"]["stream"] is True
    assert response.closed


def test_qwen_stream_read_timeout_wrapped_as_connection_error_is_not_replayed(monkeypatch):
    calls = []

    class ReadTimeoutStream(FakeStreamResponse):
        def iter_lines(self, chunk_size=128, decode_unicode=True):
            yield _sse_event({"choices": [{"index": 0, "delta": {"content": "partial"}}]})
            yield ""
            raise requests.exceptions.ConnectionError("Read timed out.")

    response = ReadTimeoutStream([])
    monkeypatch.setattr(
        "providers.cloudflare.requests.post",
        lambda url, **kwargs: (calls.append((url, kwargs)) or response),
    )
    monkeypatch.setenv("FEA_LLM_STREAMING", "true")
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "3")
    provider = CloudflareProvider("account", "token", [MODEL])

    text, error = provider.chat_text(
        [{"role": "user", "content": "Return a short answer."}],
        temperature=0.0,
        max_tokens=512,
        model=MODEL,
    )

    assert text is None
    assert "Read timeout" in error
    assert len(calls) == 1
    stats = provider.get_stats()
    assert stats["last_error_category"] == "read_timeout"
    assert stats["request_diagnostics"]["error_type"] == "ReadTimeout"
    assert stats["request_diagnostics"]["partial_output_chars"] == len("partial")
    assert stats["request_diagnostics"]["attempt_count"] == 1
    assert response.closed


def test_qwen_interrupted_stream_is_not_replayed_after_response_started(monkeypatch):
    calls = []

    class InterruptedStream(FakeStreamResponse):
        def iter_lines(self, chunk_size=128, decode_unicode=True):
            yield _sse_event({"choices": [{"index": 0, "delta": {"content": "partial"}}]})
            yield ""
            raise requests.exceptions.ChunkedEncodingError("stream ended unexpectedly")

    response = InterruptedStream([])
    monkeypatch.setattr(
        "providers.cloudflare.requests.post",
        lambda url, **kwargs: (calls.append((url, kwargs)) or response),
    )
    monkeypatch.setenv("FEA_LLM_STREAMING", "true")
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "3")
    provider = CloudflareProvider("account", "token", [MODEL])

    text, error = provider.chat_text(
        [{"role": "user", "content": "Return a short answer."}],
        temperature=0.0,
        max_tokens=512,
        model=MODEL,
    )

    assert text is None
    assert "interrupted" in error.lower()
    assert len(calls) == 1
    assert provider.get_stats()["last_error_category"] == "stream_interrupted"


def test_qwen_stream_finish_reason_length_is_preserved_for_local_validation(monkeypatch):
    response = FakeStreamResponse([
        _sse_event({"choices": [{"index": 0, "delta": {"content": '{"action":'}}]}),
        _sse_event({"choices": [{"index": 0, "delta": {}, "finish_reason": "length"}]}),
        "data: [DONE]",
    ])
    monkeypatch.setattr("providers.cloudflare.requests.post", lambda url, **kwargs: response)
    monkeypatch.setenv("FEA_LLM_STREAMING", "true")
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "token", [MODEL])

    text, error = provider.chat_text(
        [{"role": "user", "content": "Return a response."}],
        temperature=0.0,
        max_tokens=64,
        model=MODEL,
    )

    assert error is None
    assert text == '{"action":'
    stats = provider.get_stats()
    assert stats["last_finish_reason"] == "length"
    assert stats["request_diagnostics"]["finish_reason"] == "length"


def test_qwen_truncated_native_arguments_are_returned_as_inert_data_for_normalizer(monkeypatch):
    from audit_engine.semantic_audit.ae32c.response_normalizer import (
        ResponseNormalizationError,
        normalize_provider_tool_call,
    )

    response = FakeStreamResponse([
        _sse_event({"choices": [{
            "index": 0,
            "delta": {"tool_calls": [{
                "index": 0,
                "id": "call-truncated",
                "type": "function",
                "function": {
                    "name": RESPONSE_TOOL_NAME,
                    "arguments": '{"action":"tool_call","tool":"repository_summary"',
                },
            }]},
        }]}),
        _sse_event({"choices": [{"index": 0, "delta": {}, "finish_reason": "length"}]}),
        "data: [DONE]",
    ])
    monkeypatch.setattr("providers.cloudflare.requests.post", lambda url, **kwargs: response)
    monkeypatch.setenv("FEA_LLM_STREAMING", "true")
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "token", [MODEL])

    result, error = provider.chat_with_response_tool(
        [{"role": "user", "content": "Use the response function."}],
        tool_definition=build_response_tool_definition(),
        temperature=0.0,
        max_tokens=64,
        model=MODEL,
    )

    assert error is None
    assert isinstance(result, ProviderToolCall)
    assert isinstance(result.arguments, str)
    with pytest.raises(ResponseNormalizationError):
        normalize_provider_tool_call(result)
    assert provider.get_stats()["last_finish_reason"] == "length"


def test_qwen_native_tool_call_preserves_reasoning_content_and_qwen_template_defaults(monkeypatch):
    reasoning = "I should inspect the exact source evidence before choosing an action."
    response = FakeResponse({
        "id": "chatcmpl-reasoning-test",
        "choices": [{
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "content": None,
                "reasoning_content": reasoning,
                "tool_calls": [{
                    "id": "call-reasoning-test",
                    "type": "function",
                    "function": {
                        "name": RESPONSE_TOOL_NAME,
                        "arguments": json.dumps(_call_arguments()),
                    },
                }],
            },
        }],
        "usage": {"prompt_tokens": 30, "completion_tokens": 42, "total_tokens": 72},
    })
    calls = []
    monkeypatch.setattr(
        "providers.cloudflare.requests.post",
        lambda url, **kwargs: (calls.append((url, kwargs)) or response),
    )
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    monkeypatch.setenv("FEA_LLM_REASONING_EFFORT", "medium")
    provider = CloudflareProvider("account", "private-secret-value", [MODEL])

    result, error = provider.chat_with_response_tool(
        [{"role": "system", "content": "Use the response function."}],
        tool_definition=build_response_tool_definition(),
        temperature=0.0,
        max_tokens=2048,
        model=MODEL,
    )

    assert error is None
    assert isinstance(result, ProviderToolCall)
    assert result.reasoning_content == reasoning
    payload = calls[0][1]["json"]
    assert payload["chat_template_kwargs"] == {"preserve_thinking": True}
    assert payload["reasoning_effort"] == "medium"
    stats = provider.get_stats()
    assert stats["last_reasoning_content_chars"] == len(reasoning)
    assert stats["last_reasoning_content_sha256"] == hashlib.sha256(reasoning.encode()).hexdigest()
    assert reasoning not in repr(stats)
    assert response.closed


class FakeStreamingResponse:
    def __init__(self, lines, status_code=200, headers=None):
        self.lines = list(lines)
        self.status_code = status_code
        self.headers = headers or {}
        self.closed = False

    def iter_lines(self, chunk_size=128, decode_unicode=False):
        def _lines():
            for item in self.lines:
                if isinstance(item, (str, bytes)) and (b"\n" in item if isinstance(item, bytes) else "\n" in item or "\r" in item):
                    yield from item.splitlines()
                else:
                    yield item
                    yield b"" if isinstance(item, bytes) else ""
        return iter(_lines())

    def iter_content(self, chunk_size=4096, decode_unicode=False):
        for line in self.iter_lines(chunk_size=128, decode_unicode=False):
            value = line if isinstance(line, bytes) else str(line).encode("utf-8")
            yield value + b"\n"

    def close(self):
        self.closed = True


def test_qwen_streaming_tool_call_preserves_reasoning_deltas(monkeypatch):
    reasoning_parts = ["Trace the consumer first. ", "Then inspect the provider factory."]
    events = [
        {"choices": [{"index": 0, "delta": {"reasoning_content": reasoning_parts[0]}}]},
        {"choices": [{"index": 0, "delta": {
            "reasoning_content": reasoning_parts[1],
            "tool_calls": [{
                "index": 0,
                "id": "call-stream-reasoning",
                "type": "function",
                "function": {
                    "name": RESPONSE_TOOL_NAME,
                    "arguments": json.dumps(_call_arguments()),
                },
            }],
        }}]},
        {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
    ]
    lines = ["data: " + json.dumps(event) for event in events] + ["data: [DONE]"]
    response = FakeStreamingResponse(lines)
    calls = []
    monkeypatch.setattr(
        "providers.cloudflare.requests.post",
        lambda url, **kwargs: (calls.append((url, kwargs)) or response),
    )
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    monkeypatch.setenv("FEA_LLM_STREAMING", "true")
    monkeypatch.setenv("FEA_LLM_REASONING_EFFORT", "xhigh")
    provider = CloudflareProvider("account", "private-secret-value", [MODEL])

    result, error = provider.chat_with_response_tool(
        [{"role": "system", "content": "Use the response function."}],
        tool_definition=build_response_tool_definition(),
        temperature=0.0,
        max_tokens=2048,
        model=MODEL,
    )

    expected_reasoning = "".join(reasoning_parts)
    assert error is None
    assert isinstance(result, ProviderToolCall)
    assert result.reasoning_content == expected_reasoning
    payload = calls[0][1]["json"]
    assert payload["stream"] is True
    assert payload["chat_template_kwargs"] == {"preserve_thinking": True}
    assert payload["reasoning_effort"] == "xhigh"
    stats = provider.get_stats()
    assert stats["request_diagnostics"]["reasoning_effort"] == "xhigh"
    assert stats["request_diagnostics"]["reasoning_content_chars"] == len(expected_reasoning)
    assert expected_reasoning not in repr(stats)
    assert response.closed


def test_qwen_reasoning_effort_accepts_cloudflare_and_qwen_documented_levels(monkeypatch):
    monkeypatch.setenv("FEA_LLM_REASONING_EFFORT", "xhigh")
    qwen = CloudflareProvider("account", "token", [MODEL])
    assert qwen.reasoning_effort == "xhigh"
    monkeypatch.setenv("FEA_LLM_REASONING_EFFORT", "high")
    cloudflare = CloudflareProvider("account", "token", [MODEL])
    assert cloudflare.reasoning_effort == "high"


def test_qwen_empty_incomplete_stream_uses_one_bounded_non_streaming_fallback(monkeypatch):
    calls = []
    failed_stream = FakeStreamResponse([
        _sse_event({"choices": [{"index": 0, "delta": {"role": "assistant"}}]}),
    ])
    fallback = FakeResponse({
        "choices": [{
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": "RECOVERED_NON_STREAM"},
        }],
        "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
    })

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return failed_stream if len(calls) == 1 else fallback

    monkeypatch.setattr("providers.cloudflare.requests.post", fake_post)
    monkeypatch.setenv("FEA_LLM_STREAMING", "true")
    monkeypatch.setenv("FEA_LLM_STREAM_FALLBACK", "true")
    monkeypatch.setenv("FEA_LLM_STREAM_FALLBACK_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "token", [MODEL])

    text, error = provider.chat_text(
        [{"role": "user", "content": "Return a short answer."}],
        max_tokens=512,
        model=MODEL,
    )

    assert error is None
    assert text == "RECOVERED_NON_STREAM"
    assert len(calls) == 2
    assert calls[0][1]["json"]["stream"] is True
    assert calls[0][1]["stream"] is True
    assert calls[1][1]["json"]["stream"] is False
    assert calls[1][1]["stream"] is False
    assert "Accept" not in calls[1][1]["headers"]
    assert failed_stream.closed and fallback.closed
    stats = provider.get_stats()
    diag = stats["request_diagnostics"]
    assert diag["stream_error_code"] == "incomplete_stream"
    assert diag["stream_fallback_attempted"] is True
    assert diag["stream_fallback_succeeded"] is True
    assert diag["stream_fallbacks_used"] == 1
    assert diag["attempt_count"] == 2
    assert stats["successful_calls"] == 1
    assert stats["failed_calls"] == 0


def test_qwen_empty_incomplete_native_tool_stream_falls_back_without_executing_tool(monkeypatch):
    calls = []
    failed_stream = FakeStreamResponse([
        _sse_event({"choices": [{"index": 0, "delta": {"role": "assistant"}}]}),
    ])
    fallback = FakeResponse({
        "choices": [{
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call-fallback",
                    "type": "function",
                    "function": {
                        "name": RESPONSE_TOOL_NAME,
                        "arguments": json.dumps(_call_arguments()),
                    },
                }],
            },
        }],
    })

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return failed_stream if len(calls) == 1 else fallback

    monkeypatch.setattr("providers.cloudflare.requests.post", fake_post)
    monkeypatch.setenv("FEA_LLM_STREAMING", "true")
    monkeypatch.setenv("FEA_LLM_STREAM_FALLBACK", "true")
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "token", [MODEL])

    result, error = provider.chat_with_response_tool(
        [{"role": "system", "content": "Use the response function."}],
        tool_definition=build_response_tool_definition(),
        model=MODEL,
    )

    assert error is None
    assert isinstance(result, ProviderToolCall)
    assert result.arguments == _call_arguments()
    assert len(calls) == 2
    assert calls[1][1]["json"]["stream"] is False
    expected_fallback_payload = dict(calls[0][1]["json"])
    expected_fallback_payload["stream"] = False
    assert calls[1][1]["json"] == expected_fallback_payload
    assert provider.get_stats()["request_diagnostics"]["stream_fallback_succeeded"] is True
    assert provider.get_stats()["native_tool_call_responses"] == 1


def test_qwen_partial_content_stream_is_never_replayed_by_fallback(monkeypatch):
    calls = []
    response = FakeStreamResponse([
        _sse_event({"choices": [{"index": 0, "delta": {"content": "partial answer"}}]}),
    ])
    monkeypatch.setattr(
        "providers.cloudflare.requests.post",
        lambda url, **kwargs: (calls.append((url, kwargs)) or response),
    )
    monkeypatch.setenv("FEA_LLM_STREAMING", "true")
    monkeypatch.setenv("FEA_LLM_STREAM_FALLBACK", "true")
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "3")
    provider = CloudflareProvider("account", "token", [MODEL])

    text, error = provider.chat_text(
        [{"role": "user", "content": "Return a short answer."}],
        max_tokens=512,
        model=MODEL,
    )

    assert text is None
    assert "incomplete" in error.lower()
    assert len(calls) == 1
    diag = provider.get_stats()["request_diagnostics"]
    assert diag["stream_fallback_attempted"] is False
    assert diag["partial_output_chars"] == len("partial answer")
    assert diag["stream_error_code"] == "incomplete_stream"


def test_qwen_reasoning_only_incomplete_stream_is_not_replayed(monkeypatch):
    calls = []
    response = FakeStreamResponse([
        _sse_event({"choices": [{"index": 0, "delta": {"reasoning_content": "partial thinking"}}]}),
    ])
    monkeypatch.setattr(
        "providers.cloudflare.requests.post",
        lambda url, **kwargs: (calls.append((url, kwargs)) or response),
    )
    monkeypatch.setenv("FEA_LLM_STREAMING", "true")
    monkeypatch.setenv("FEA_LLM_STREAM_FALLBACK", "true")
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "token", [MODEL])

    text, error = provider.chat_text(
        [{"role": "user", "content": "Return a short answer."}],
        max_tokens=512,
        model=MODEL,
    )

    assert text is None
    assert "incomplete" in error.lower()
    assert len(calls) == 1
    diag = provider.get_stats()["request_diagnostics"]
    assert diag["stream_reasoning_chars"] == len("partial thinking")
    assert diag["stream_fallback_attempted"] is False


def test_cloudflare_stream_fallback_is_capped_at_one_per_provider_instance(monkeypatch):
    calls = []
    stream_responses = [
        FakeStreamResponse([_sse_event({"choices": [{"index": 0, "delta": {"role": "assistant"}}]})]),
        FakeStreamResponse([_sse_event({"choices": [{"index": 0, "delta": {"role": "assistant"}}]})]),
    ]
    fallback = FakeResponse({
        "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "first recovered"}}],
    })

    def fake_post(url, **kwargs):
        calls.append(kwargs)
        if kwargs["json"]["stream"]:
            return stream_responses.pop(0)
        return fallback

    monkeypatch.setattr("providers.cloudflare.requests.post", fake_post)
    monkeypatch.setenv("FEA_LLM_STREAMING", "true")
    monkeypatch.setenv("FEA_LLM_STREAM_FALLBACK", "true")
    monkeypatch.setenv("FEA_LLM_STREAM_FALLBACK_MAX_ATTEMPTS", "5")
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "token", [MODEL])

    first, first_error = provider.chat_text([{"role": "user", "content": "first"}], model=MODEL)
    second, second_error = provider.chat_text([{"role": "user", "content": "second"}], model=MODEL)

    assert first == "first recovered" and first_error is None
    assert second is None and "incomplete" in second_error.lower()
    assert len(calls) == 3
    assert provider.stream_fallbacks_used == 1
    assert provider.max_stream_fallbacks == 1


def test_qwen_partial_tool_call_delta_is_never_replayed_or_returned(monkeypatch):
    calls = []
    response = FakeStreamResponse([
        _sse_event({"choices": [{
            "index": 0,
            "delta": {"tool_calls": [{
                "index": 0,
                "id": "partial-call",
                "type": "function",
                "function": {
                    "name": RESPONSE_TOOL_NAME,
                    "arguments": '{"action":"tool_call"',
                },
            }]},
        }]}),
    ])
    monkeypatch.setattr(
        "providers.cloudflare.requests.post",
        lambda url, **kwargs: (calls.append((url, kwargs)) or response),
    )
    monkeypatch.setenv("FEA_LLM_STREAMING", "true")
    monkeypatch.setenv("FEA_LLM_STREAM_FALLBACK", "true")
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "2")
    provider = CloudflareProvider("account", "token", [MODEL])

    result, error = provider.chat_with_response_tool(
        [{"role": "system", "content": "Use the response function."}],
        tool_definition=build_response_tool_definition(),
        model=MODEL,
    )

    assert result is None
    assert error is not None
    assert len(calls) == 1
    diag = provider.get_stats()["request_diagnostics"]
    assert diag["stream_tool_call_delta_count"] == 1
    assert diag["stream_fallback_attempted"] is False
    assert provider.get_stats()["native_tool_call_responses"] == 0


def test_qwen_reasoning_only_non_streaming_response_is_not_accepted_as_action(monkeypatch):
    reasoning = "The model emitted internal reasoning but no action."
    response = FakeResponse({
        "choices": [{
            "finish_reason": "stop",
            "message": {
                "role": "assistant",
                "content": None,
                "reasoning_content": reasoning,
            },
        }],
    })
    monkeypatch.setattr("providers.cloudflare.requests.post", lambda *a, **k: response)
    monkeypatch.setenv("FEA_LLM_STREAMING", "false")
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "token", [MODEL])

    result, error = provider.chat_with_response_tool(
        [{"role": "system", "content": "Use the response function."}],
        tool_definition=build_response_tool_definition(),
        model=MODEL,
    )

    assert result is None
    assert "reasoning without a usable response action" in error
    stats = provider.get_stats()
    assert stats["last_error_category"] == "empty_reasoning_only_response"
    assert stats["request_diagnostics"]["error_type"] == "EmptyModelResponse"
    assert reasoning not in repr(stats)
    assert response.closed



def test_sse_parser_accumulates_multiline_data_fields_before_json_decode(monkeypatch):
    payload = (
        'data: {"choices":[\r\n'
        'data: {"index":0,"delta":{"content":"MULTILINE_OK"},"finish_reason":"stop"}]}\r\n'
        '\r\n'
        'data: [DONE]\r\n\r\n'
    )
    response = FakeStreamResponse([payload])
    monkeypatch.setattr("providers.cloudflare.requests.post", lambda *a, **k: response)
    monkeypatch.setenv("FEA_LLM_STREAMING", "true")
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "token", [MODEL])

    text, error = provider.chat_text([{"role": "user", "content": "test"}], model=MODEL)

    assert error is None
    assert text == "MULTILINE_OK"
    assert response.closed


def test_sse_parser_handles_bom_comments_crlf_and_usage_only_chunk(monkeypatch):
    payload = (
        '\ufeff: heartbeat\r\n'
        'data: {"choices":[{"index":0,"delta":{"content":"BOM_OK"},"finish_reason":"stop"}]}\r\n\r\n'
        'data: {"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":2,"total_tokens":5}}\r\n\r\n'
        'data: [DONE]\r\n\r\n'
    )
    response = FakeStreamResponse([payload])
    monkeypatch.setattr("providers.cloudflare.requests.post", lambda *a, **k: response)
    monkeypatch.setenv("FEA_LLM_STREAMING", "true")
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "token", [MODEL])

    text, error = provider.chat_text([{"role": "user", "content": "test"}], model=MODEL)

    assert error is None
    assert text == "BOM_OK"
    assert provider.get_stats()["usage"]["total_tokens"] == 5


def test_sse_parser_rejects_non_string_content_with_safe_fingerprint(monkeypatch):
    response = FakeStreamResponse([
        _sse_event({"choices": [{"index": 0, "delta": {"content": 123}}]}),
        "data: [DONE]",
    ], headers={"Content-Type": "text/event-stream", "Content-Encoding": "identity", "Transfer-Encoding": "chunked", "CF-Ray": "abc12345"})
    monkeypatch.setattr("providers.cloudflare.requests.post", lambda *a, **k: response)
    monkeypatch.setenv("FEA_LLM_STREAMING", "true")
    monkeypatch.setenv("FEA_LLM_STREAM_FALLBACK", "false")
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "token", [MODEL])

    text, error = provider.chat_text([{"role": "user", "content": "test"}], model=MODEL)

    assert text is None
    assert "Invalid or incomplete provider stream" in error
    diag = provider.get_stats()["request_diagnostics"]
    assert diag["stream_error_code"] == "invalid_stream_content_type"
    assert diag["stream_error_payload_sha256"]
    assert len(diag["stream_error_payload_sha256"]) == 64
    assert diag["stream_content_type"] == "text/event-stream"
    assert diag["stream_content_encoding"] == "identity"
    assert diag["stream_transfer_encoding"] == "chunked"
    assert '{"choices":[{"index":0,"delta":{"content":123}}]}' not in repr(diag)


def test_qwen_reasoning_only_malformed_stream_uses_one_bounded_recovery(monkeypatch):
    calls = []
    failed_stream = FakeStreamResponse([
        _sse_event({"choices": [{"index": 0, "delta": {"reasoning_content": "partial internal reasoning"}}]}),
        "data: {malformed-json",
    ], headers={"Content-Type": "text/event-stream", "CF-Ray": "ray123456789"})
    fallback = FakeResponse({
        "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "RECOVERED_FINAL"}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
    })

    def fake_post(url, **kwargs):
        calls.append(kwargs)
        return failed_stream if len(calls) == 1 else fallback

    monkeypatch.setattr("providers.cloudflare.requests.post", fake_post)
    monkeypatch.setenv("FEA_LLM_STREAMING", "true")
    monkeypatch.setenv("FEA_LLM_STREAM_FALLBACK", "true")
    monkeypatch.setenv("FEA_LLM_STREAM_FALLBACK_ALLOW_REASONING_ONLY", "true")
    monkeypatch.setenv("FEA_LLM_STREAM_FALLBACK_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "token", [MODEL])

    text, error = provider.chat_text([{"role": "user", "content": "test"}], model=MODEL)

    assert error is None
    assert text == "RECOVERED_FINAL"
    assert len(calls) == 2
    assert calls[0]["json"]["stream"] is True
    assert calls[1]["json"]["stream"] is False
    assert calls[1]["json"]["messages"] == calls[0]["json"]["messages"]
    assert failed_stream.closed and fallback.closed
    diag = provider.get_stats()["request_diagnostics"]
    assert diag["stream_reasoning_chars"] == len("partial internal reasoning")
    assert diag["stream_error_code"] == "malformed_stream_event"
    assert diag["stream_error_event_index"] == 2
    assert diag["stream_error_payload_bytes"] > 0
    assert len(diag["stream_error_payload_sha256"]) == 64
    assert diag["stream_json_error_position"] is not None
    assert diag["stream_request_id"] == "ray123456789"
    assert diag["stream_fallback_attempted"] is True
    assert diag["stream_fallback_succeeded"] is True
    assert diag["stream_fallback_reason"] == "malformed_stream_event"
    assert "partial internal reasoning" not in repr(provider.get_stats())


def test_reasoning_only_recovery_is_disabled_without_explicit_flag(monkeypatch):
    calls = []
    stream = FakeStreamResponse([
        _sse_event({"choices": [{"index": 0, "delta": {"reasoning_content": "private partial"}}]}),
        "data: {malformed",
    ])
    monkeypatch.setattr("providers.cloudflare.requests.post", lambda *a, **k: (calls.append(k) or stream))
    monkeypatch.setenv("FEA_LLM_STREAMING", "true")
    monkeypatch.setenv("FEA_LLM_STREAM_FALLBACK", "true")
    monkeypatch.delenv("FEA_LLM_STREAM_FALLBACK_ALLOW_REASONING_ONLY", raising=False)
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "token", [MODEL])

    result, error = provider.chat_text([{"role": "user", "content": "test"}], model=MODEL)

    assert result is None
    assert len(calls) == 1
    assert provider.get_stats()["request_diagnostics"]["stream_fallback_attempted"] is False


def test_reasoning_only_recovery_never_replays_partial_content_or_tool_calls(monkeypatch):
    for delta in (
        {"content": "partial visible answer"},
        {"tool_calls": [{"index": 0, "id": "partial", "function": {"arguments": "{"}}]},
    ):
        calls = []
        stream = FakeStreamResponse([
            _sse_event({"choices": [{"index": 0, "delta": delta}]}),
            "data: {malformed",
        ])
        monkeypatch.setattr("providers.cloudflare.requests.post", lambda *a, **k: (calls.append(k) or stream))
        monkeypatch.setenv("FEA_LLM_STREAMING", "true")
        monkeypatch.setenv("FEA_LLM_STREAM_FALLBACK", "true")
        monkeypatch.setenv("FEA_LLM_STREAM_FALLBACK_ALLOW_REASONING_ONLY", "true")
        monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
        provider = CloudflareProvider("account", "token", [MODEL])
        result, error = provider.chat_text([{"role": "user", "content": "test"}], model=MODEL)
        assert result is None
        assert len(calls) == 1
        assert provider.get_stats()["request_diagnostics"]["stream_fallback_attempted"] is False



def test_sse_parser_rejects_wrong_content_type_before_consuming_body(monkeypatch):
    response = FakeStreamResponse([
        _sse_event({"choices": [{"index": 0, "delta": {"content": "SHOULD_NOT_BE_READ"}}]}),
    ], headers={"Content-Type": "application/json"})
    calls = []
    monkeypatch.setattr("providers.cloudflare.requests.post", lambda *a, **k: (calls.append(k) or response))
    monkeypatch.setenv("FEA_LLM_STREAMING", "true")
    monkeypatch.setenv("FEA_LLM_STREAM_FALLBACK", "false")
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "token", [MODEL])

    result, error = provider.chat_text([{"role": "user", "content": "test"}], model=MODEL)

    assert result is None
    assert "Invalid or incomplete provider stream" in error
    assert provider.get_stats()["request_diagnostics"]["stream_error_code"] == "unexpected_stream_content_type"
    assert response.closed



def test_sse_parser_handles_crlf_and_utf8_codepoint_split_across_transport_chunks(monkeypatch):
    class RawChunkResponse(FakeResponse):
        def __init__(self, chunks):
            super().__init__({}, headers={"Content-Type": "text/event-stream"})
            self.chunks = chunks
            self.chunk_sizes = []

        def iter_content(self, chunk_size=4096, decode_unicode=False):
            self.chunk_sizes.append(chunk_size)
            yield from self.chunks

    payload = '{"choices":[{"index":0,"delta":{"content":"café 😀"},"finish_reason":"stop"}]}'
    raw = ("\ufeffdata: " + payload + "\r\n\r\ndata: [DONE]\r\n\r\n").encode("utf-8")
    split_at = raw.index("😀".encode("utf-8")) + 2
    response = RawChunkResponse([raw[:split_at], raw[split_at:split_at + 1], raw[split_at + 1:]])
    monkeypatch.setattr("providers.cloudflare.requests.post", lambda *a, **k: response)
    monkeypatch.setenv("FEA_LLM_STREAMING", "true")
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "token", [MODEL])

    text, error = provider.chat_text([{"role": "user", "content": "test"}], model=MODEL)

    assert error is None
    assert text == "café 😀"
    assert response.chunk_sizes == [4096]
    assert response.closed


def test_sse_parser_discards_unterminated_event_at_eof_as_incomplete(monkeypatch):
    class RawChunkResponse(FakeResponse):
        def iter_content(self, chunk_size=4096, decode_unicode=False):
            yield b'data: {"choices":[{"index":0,"delta":{"content":"not-dispatched"},"finish_reason":"stop"}]}'

    response = RawChunkResponse({}, headers={"Content-Type": "text/event-stream"})
    monkeypatch.setattr("providers.cloudflare.requests.post", lambda *a, **k: response)
    monkeypatch.setenv("FEA_LLM_STREAMING", "true")
    monkeypatch.setenv("FEA_LLM_STREAM_FALLBACK", "false")
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "token", [MODEL])

    result, error = provider.chat_text([{"role": "user", "content": "test"}], model=MODEL)

    assert result is None
    assert "Invalid or incomplete provider stream" in error
    assert provider.get_stats()["request_diagnostics"]["stream_error_code"] == "incomplete_stream"
    assert provider.get_stats()["request_diagnostics"]["partial_output_chars"] == 0


def test_successful_done_sentinel_is_not_reported_as_error_payload(monkeypatch):
    payload = (
        _sse_event({"choices": [{"index": 0, "delta": {"content": "DONE_OK"}, "finish_reason": "stop"}]})
        + "\n\ndata: [DONE]\n\n"
    )
    response = FakeStreamResponse([payload], headers={"Content-Type": "text/event-stream"})
    monkeypatch.setattr("providers.cloudflare.requests.post", lambda *a, **k: response)
    monkeypatch.setenv("FEA_LLM_STREAMING", "true")
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    provider = CloudflareProvider("account", "token", [MODEL])

    result, error = provider.chat_text([{"role": "user", "content": "test"}], model=MODEL)

    assert error is None
    assert result == "DONE_OK"
    diagnostics = provider.get_stats()["request_diagnostics"]
    assert diagnostics["terminal_sentinel_observed"] is True
    assert diagnostics["stream_error_payload_sha256"] == ""
    assert diagnostics["stream_error_payload_bytes"] == 0
    assert diagnostics["stream_error_event_index"] == 0
