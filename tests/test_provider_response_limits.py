"""Tests for bounded provider response parsing; no network calls are made."""
from __future__ import annotations

from providers.cloudflare import CloudflareProvider
from providers.openai_compatible import OpenAICompatibleProvider
from providers.response_limits import ProviderResponseTooLarge, load_bounded_json
import pytest


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.headers = {}
        self.closed = False

    def json(self):
        return self.payload

    def close(self):
        self.closed = True


def openai_payload(content):
    return {
        "model": "test-model",
        "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def test_bounded_json_reader_rejects_oversized_mock_payload_and_closes_response():
    response = FakeResponse({"content": "x" * 2_000})
    with pytest.raises(ProviderResponseTooLarge):
        load_bounded_json(response, max_bytes=256)
    assert response.closed


class StreamResponse(FakeResponse):
    def __init__(self, body, status_code=200):
        super().__init__({}, status_code=status_code)
        self.body = body

    def iter_content(self, chunk_size=8192):
        for index in range(0, len(self.body), max(1, chunk_size // 2)):
            yield self.body[index:index + max(1, chunk_size // 2)]

    def json(self):
        raise AssertionError("streaming responses must be parsed from bounded bytes")


def test_streaming_json_reader_accepts_bounded_json_and_closes_response():
    response = StreamResponse(b'{"ok":true,"count":3}')
    assert load_bounded_json(response, max_bytes=100) == {"ok": True, "count": 3}
    assert response.closed


def test_streaming_json_reader_stops_when_body_exceeds_byte_limit():
    response = StreamResponse(b'{"value":"' + b"x" * 500 + b'"}')
    with pytest.raises(ProviderResponseTooLarge):
        load_bounded_json(response, max_bytes=100)
    assert response.closed


def test_openai_compatible_provider_rejects_oversized_response_body(monkeypatch):
    monkeypatch.delenv("FEA_BENCHMARK_MODE", raising=False)
    monkeypatch.delenv("FEA_BENCHMARK_FORCE_MAX_TOKENS", raising=False)
    response = FakeResponse(openai_payload("x" * 2_000))
    monkeypatch.setattr("providers.openai_compatible.requests.post", lambda *args, **kwargs: response)
    provider = OpenAICompatibleProvider("openrouter", "synthetic-secret", "test-model", max_retries=1, max_response_bytes=256)
    text, error = provider.chat([{"role": "user", "content": "hello"}])
    assert text is None
    assert "size limit" in error
    assert response.closed


def test_openai_compatible_provider_rejects_oversized_decoded_text(monkeypatch):
    monkeypatch.delenv("FEA_BENCHMARK_MODE", raising=False)
    monkeypatch.delenv("FEA_BENCHMARK_FORCE_MAX_TOKENS", raising=False)
    response = FakeResponse(openai_payload("x" * 300))
    monkeypatch.setattr("providers.openai_compatible.requests.post", lambda *args, **kwargs: response)
    provider = OpenAICompatibleProvider("nararouter", "synthetic-secret", "test-model", max_retries=1, max_response_bytes=10_000, max_response_chars=100)
    text, error = provider.chat([{"role": "user", "content": "hello"}])
    assert text is None
    assert "character limit" in error
    assert response.closed


def test_cloudflare_provider_rejects_oversized_decoded_text(monkeypatch):
    monkeypatch.delenv("FEA_BENCHMARK_MODE", raising=False)
    monkeypatch.delenv("FEA_BENCHMARK_FORCE_MAX_TOKENS", raising=False)
    response = FakeResponse({"success": True, "result": {"response": "short"}})
    monkeypatch.setattr("providers.cloudflare.requests.post", lambda *args, **kwargs: response)
    provider = CloudflareProvider("account", "synthetic-token", ["test-model"], max_logical_calls=2, max_response_chars=4)
    provider.extractor.extract = lambda *args, **kwargs: "x" * 5
    text, error = provider.chat([{"role": "user", "content": "hello"}], max_tokens=100)
    assert text is None
    assert "character limit" in error
    assert response.closed


def test_provider_error_does_not_include_upstream_response_body(monkeypatch):
    monkeypatch.delenv("FEA_BENCHMARK_MODE", raising=False)
    monkeypatch.delenv("FEA_BENCHMARK_FORCE_MAX_TOKENS", raising=False)
    response = FakeResponse({"error": {"message": "sk-ABCDEFGHIJKLMNOPQRSTUVWX"}}, status_code=400)
    monkeypatch.setattr("providers.openai_compatible.requests.post", lambda *args, **kwargs: response)
    provider = OpenAICompatibleProvider("openrouter", "synthetic-secret", "test-model", max_retries=1)
    text, error = provider.chat([{"role": "user", "content": "hello"}])
    assert text is None
    assert "sk-ABCDEFGHIJKLMNOPQRSTUVWX" not in error
    assert "HTTP 400" in error
    assert response.closed


def test_cloudflare_http_error_omits_upstream_body(monkeypatch):
    monkeypatch.delenv("FEA_BENCHMARK_MODE", raising=False)
    monkeypatch.delenv("FEA_BENCHMARK_FORCE_MAX_TOKENS", raising=False)
    response = FakeResponse({"error": "sk-ABCDEFGHIJKLMNOPQRSTUVWX"}, status_code=400)
    monkeypatch.setattr("providers.cloudflare.requests.post", lambda *args, **kwargs: response)
    provider = CloudflareProvider("account", "synthetic-token", ["test-model"], max_logical_calls=2)
    text, error = provider.chat([{"role": "user", "content": "hello"}], max_tokens=100)
    assert text is None
    assert "sk-ABCDEFGHIJKLMNOPQRSTUVWX" not in error
    assert "body omitted" in error
    assert response.closed
