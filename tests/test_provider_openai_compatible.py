from types import SimpleNamespace

import pytest

from providers.openai_compatible import OpenAICompatibleProvider


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload


def success_payload(content="ok", model="test-model"):
    return {
        "id": "chatcmpl-test",
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 17, "completion_tokens": 23, "total_tokens": 40},
    }


def test_nararouter_uses_explicit_endpoint_model_and_bearer_auth(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(payload=success_payload("Nara answer", "agnes-2.5-flash"))

    monkeypatch.setattr("providers.openai_compatible.requests.post", fake_post)
    provider = OpenAICompatibleProvider("nararouter", "secret-value", "agnes-2.5-flash")
    text, error = provider.chat([{"role": "user", "content": "hello"}], max_tokens=8000)

    assert text == "Nara answer"
    assert error is None
    assert calls[0][0] == "https://router.bynara.id/v1/chat/completions"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer secret-value"
    assert calls[0][1]["json"]["model"] == "agnes-2.5-flash"
    assert calls[0][1]["json"]["max_tokens"] == 8000
    stats = provider.get_stats()
    assert stats["successful_calls"] == 1
    assert stats["usage"]["total_tokens"] == 40
    assert "secret-value" not in repr(stats)


def test_openrouter_accepts_list_content_and_tracks_usage(monkeypatch):
    def fake_post(url, **kwargs):
        assert url == "https://openrouter.ai/api/v1/chat/completions"
        assert kwargs["headers"]["X-Title"] == "Finite Element Analysis Pipeline"
        return FakeResponse(payload={
            "model": "deepseek/deepseek-v4.1-flash-1017",
            "choices": [{"message": {"content": [{"type": "text", "text": "valid "}, {"type": "text", "text": "content"}]}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        })

    monkeypatch.setattr("providers.openai_compatible.requests.post", fake_post)
    provider = OpenAICompatibleProvider("openrouter", "openrouter-secret", "deepseek/deepseek-v4.1-flash-1017")
    text, error = provider.chat([{"role": "user", "content": "hello"}])
    assert text == "valid content"
    assert error is None
    assert provider.get_stats()["usage"]["total_tokens"] == 150


def test_retry_after_is_bounded_and_transient_429_can_recover(monkeypatch):
    responses = [
        FakeResponse(status_code=429, payload={"error": "busy"}, headers={"Retry-After": "999"}),
        FakeResponse(payload=success_payload()),
    ]
    calls = []
    sleeps = []

    def fake_post(url, **kwargs):
        calls.append(url)
        return responses.pop(0)

    monkeypatch.setattr("providers.openai_compatible.requests.post", fake_post)
    monkeypatch.setattr("providers.openai_compatible.time.sleep", sleeps.append)
    provider = OpenAICompatibleProvider("openrouter", "key", "model", max_retries=2)
    text, error = provider.chat([{"role": "user", "content": "hello"}])
    assert text == "ok"
    assert error is None
    assert len(calls) == 2
    assert sleeps == [60]
    assert provider.get_stats()["http_attempts"] == 2


def test_missing_choices_is_reported_with_http_status_without_response_dump(monkeypatch):
    monkeypatch.setattr(
        "providers.openai_compatible.requests.post",
        lambda *args, **kwargs: FakeResponse(status_code=200, payload={"error": {"message": "no choices"}}),
    )
    provider = OpenAICompatibleProvider("nararouter", "secret", "agnes-2.5-flash", max_retries=1)
    text, error = provider.chat([{"role": "user", "content": "hello"}])
    assert text is None
    assert "missing choices" in error
    assert "HTTP 200" in error
    assert "secret" not in error
    stats = provider.get_stats()
    assert stats["failed_calls"] == 1
    assert stats["last_error_code"] == "malformed_completion_envelope"
    assert stats["error_counts"] == {"malformed_completion_envelope": 1}


def test_http_api_error_payload_is_classified_without_echoing_payload(monkeypatch):
    monkeypatch.setattr(
        "providers.openai_compatible.requests.post",
        lambda *args, **kwargs: FakeResponse(
            status_code=400,
            payload={"error": {"message": "private upstream detail", "token": "must-not-leak"}},
        ),
    )
    provider = OpenAICompatibleProvider("openrouter", "secret", "model", max_retries=1)
    text, error = provider.chat([{"role": "user", "content": "hello"}])
    stats = provider.get_stats()

    assert text is None
    assert "HTTP 400" in error
    assert "private upstream detail" not in error
    assert "must-not-leak" not in repr(stats)
    assert stats["last_error_code"] == "provider_api_error_payload"
    assert stats["error_counts"] == {"provider_api_error_payload": 1}


def test_benchmark_mode_forces_requested_token_ceiling(monkeypatch):
    seen = []
    monkeypatch.setenv("FEA_BENCHMARK_MODE", "1")
    monkeypatch.setenv("FEA_BENCHMARK_FORCE_MAX_TOKENS", "1")
    monkeypatch.setenv("FEA_MAX_TOKENS_PER_CALL", "8000")
    monkeypatch.setattr(
        "providers.openai_compatible.requests.post",
        lambda url, **kwargs: (seen.append(kwargs["json"]["max_tokens"]) or FakeResponse(payload=success_payload())),
    )
    provider = OpenAICompatibleProvider("openrouter", "key", "model", max_retries=1)
    provider.chat([{"role": "user", "content": "hello"}], max_tokens=500)
    assert seen == [8000]


def test_logical_call_budget_is_enforced(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "providers.openai_compatible.requests.post",
        lambda *args, **kwargs: (calls.append(1) or FakeResponse(payload=success_payload())),
    )
    provider = OpenAICompatibleProvider("nararouter", "key", "model", max_logical_calls=1)
    assert provider.chat([{"role": "user", "content": "one"}])[1] is None
    text, error = provider.chat([{"role": "user", "content": "two"}])
    assert text is None
    assert "budget exhausted" in error
    assert len(calls) == 1


def test_total_calls_is_compatibility_alias_for_logical_calls(monkeypatch):
    monkeypatch.setattr(
        "providers.openai_compatible.requests.post",
        lambda *args, **kwargs: FakeResponse(payload=success_payload()),
    )
    provider = OpenAICompatibleProvider("nararouter", "key", "agnes-2.5-flash", max_retries=1)
    assert provider.total_calls == 0
    provider.chat([{"role": "user", "content": "hello"}])
    assert provider.total_calls == 1
    assert provider.total_calls == provider.logical_calls
    assert provider.get_stats()["total_calls"] == provider.total_calls


@pytest.mark.parametrize("finish_reason,error_code", [
    ("length", "completion_truncated"),
    ("max_tokens", "completion_truncated"),
    ("content_filter", "completion_filtered"),
    ("safety", "completion_filtered"),
])
def test_finish_reason_rejects_incomplete_or_filtered_response(monkeypatch, finish_reason, error_code):
    payload = success_payload(content='{"action":"final"')
    payload["choices"][0]["finish_reason"] = finish_reason
    monkeypatch.setattr("providers.openai_compatible.requests.post", lambda *a, **k: FakeResponse(payload=payload))
    provider = OpenAICompatibleProvider("openrouter", "secret", "test-model", max_retries=1)
    text, error = provider.chat([{"role": "user", "content": "hello"}])
    assert text is None
    assert "secret" not in error
    assert "action" not in error
    stats = provider.get_stats()
    assert stats["last_error_code"] == error_code
    assert stats["failed_calls"] == 1
    assert stats["finish_reason_counts"] == {finish_reason: 1}
    assert stats["successful_calls"] == 0


def test_absent_finish_reason_keeps_legacy_success_behavior(monkeypatch):
    payload = success_payload("plain response without a finish reason")
    del payload["choices"][0]["finish_reason"]
    monkeypatch.setattr("providers.openai_compatible.requests.post", lambda *a, **k: FakeResponse(payload=payload))
    provider = OpenAICompatibleProvider("nararouter", "secret", "model", max_retries=1)
    content, error = provider.chat([{"role": "user", "content": "test"}])
    assert error is None
    assert content == "plain response without a finish reason"
    assert provider.get_stats()["finish_reason_counts"] == {"unknown": 1}



def test_openrouter_documented_model_uses_json_object_mode_and_requires_parameter(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(payload=success_payload("{}", "nvidia/nemotron-3.5-super-vl:free"))

    monkeypatch.setattr("providers.openai_compatible.requests.post", fake_post)
    provider = OpenAICompatibleProvider(
        "openrouter", "key", "nvidia/nemotron-3.5-super-vl:free", max_retries=1
    )

    assert provider.get_capabilities()["json_object_mode"] is True
    content, error = provider.chat_structured([{"role": "user", "content": "Return JSON."}])

    assert error is None
    assert content == "{}"
    payload = calls[0][1]["json"]
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["provider"] == {"require_parameters": True}
    assert provider.get_stats()["structured_json_calls"] == 1


def test_openrouter_gemma_free_model_is_declared_json_object_compatible():
    provider = OpenAICompatibleProvider(
        "openrouter", "key", "google/gemma-4-31b-it:free"
    )
    assert provider.get_capabilities()["json_object_mode"] is True


def test_openrouter_unknown_model_does_not_claim_json_object_support():
    provider = OpenAICompatibleProvider("openrouter", "key", "unverified/model")
    assert provider.get_capabilities()["json_object_mode"] is False


def test_nararouter_json_object_mode_is_fail_closed_and_requires_opt_in(monkeypatch):
    monkeypatch.delenv("FEA_NARAROUTER_JSON_OBJECT_MODE", raising=False)
    provider = OpenAICompatibleProvider("nararouter", "key", "laguna-s-2.1")
    assert provider.get_capabilities()["json_object_mode"] is False

    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(payload=success_payload("{}", "laguna-s-2.1"))

    monkeypatch.setattr("providers.openai_compatible.requests.post", fake_post)
    monkeypatch.setenv("FEA_NARAROUTER_JSON_OBJECT_MODE", "1")
    assert provider.get_capabilities()["json_object_mode"] is True
    content, error = provider.chat_structured([{"role": "user", "content": "Return JSON."}])

    assert error is None
    assert content == "{}"
    assert calls[0][1]["json"]["response_format"] == {"type": "json_object"}
    assert "provider" not in calls[0][1]["json"]


def test_unsupported_response_format_is_rejected_without_http_call(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "providers.openai_compatible.requests.post",
        lambda *args, **kwargs: calls.append(1),
    )
    provider = OpenAICompatibleProvider("openrouter", "key", "test-model", max_retries=1)
    content, error = provider.chat(
        [{"role": "user", "content": "hello"}],
        response_format={"type": "json_schema"},
    )
    assert content is None
    assert error is not None
    assert provider.get_stats()["last_error_code"] == "unsupported_response_format"
    assert calls == []
