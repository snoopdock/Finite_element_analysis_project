"""Regression tests for Cloudflare provider response safety and limits."""

from providers.cloudflare import CloudflareProvider


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class ErrorResponseWithoutText:
    status_code = 400

    def json(self):
        raise AssertionError("HTTP error response body must not be parsed")


def test_http_error_is_body_free_and_does_not_require_text(monkeypatch):
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    monkeypatch.setattr(
        "providers.cloudflare.requests.post",
        lambda *args, **kwargs: ErrorResponseWithoutText(),
    )
    provider = CloudflareProvider(
        "account",
        "synthetic-token",
        ["test-model"],
        max_logical_calls=1,
    )

    text, error = provider.chat([{"role": "user", "content": "hello"}])

    assert text is None
    assert error == "HTTP 400: upstream error body omitted"
    assert "synthetic-token" not in error


def test_decoded_response_above_configured_limit_is_rejected(monkeypatch):
    monkeypatch.delenv("FEA_BENCHMARK_MODE", raising=False)
    monkeypatch.delenv("FEA_BENCHMARK_FORCE_MAX_TOKENS", raising=False)
    response = FakeResponse({"success": True, "result": {"response": "short"}})
    monkeypatch.setattr(
        "providers.cloudflare.requests.post",
        lambda *args, **kwargs: response,
    )
    provider = CloudflareProvider(
        "account",
        "synthetic-token",
        ["test-model"],
        max_logical_calls=1,
        max_response_chars=4,
    )

    text, error = provider.chat([{"role": "user", "content": "hello"}])

    assert text is None
    assert error == "Decoded response exceeds max_response_chars limit (5 > 4)"
    stats = provider.get_stats()
    assert stats["max_response_chars"] == 4
    assert stats["oversized_responses"] == 1
    assert stats["successful_calls"] == 0
    assert stats["failed_calls"] == 1


def test_response_at_configured_limit_is_accepted(monkeypatch):
    response = FakeResponse({"success": True, "result": {"response": "okay"}})
    monkeypatch.setattr(
        "providers.cloudflare.requests.post",
        lambda *args, **kwargs: response,
    )
    provider = CloudflareProvider(
        "account",
        "synthetic-token",
        ["test-model"],
        max_logical_calls=1,
        max_response_chars=4,
    )

    text, error = provider.chat([{"role": "user", "content": "hello"}])

    assert text == "okay"
    assert error is None
    assert provider.get_stats()["successful_calls"] == 1


def test_structured_chat_keeps_json_object_response_format(monkeypatch):
    captured = {}
    response = FakeResponse({"success": True, "result": {"response": '{"kind":"final"}'}})

    def fake_post(*args, **kwargs):
        captured.update(kwargs)
        return response

    monkeypatch.setattr("providers.cloudflare.requests.post", fake_post)
    provider = CloudflareProvider(
        "account",
        "synthetic-token",
        ["test-model"],
        max_logical_calls=1,
    )

    text, error = provider.chat_structured(
        [{"role": "user", "content": "return a JSON object"}]
    )

    assert error is None
    assert text == '{"kind":"final"}'
    assert captured["json"]["response_format"] == {"type": "json_object"}
    assert provider.get_stats()["structured_json_calls"] == 1
