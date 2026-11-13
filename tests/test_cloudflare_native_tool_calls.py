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
