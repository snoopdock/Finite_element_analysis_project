"""Provider error redaction tests for AE-32C Patch 1; no live network calls."""
from __future__ import annotations

from providers.cloudflare import CloudflareProvider
from providers.openai_compatible import OpenAICompatibleProvider


class FakeErrorResponse:
    status_code = 400
    text = 'upstream echoed Authorization: Bearer synthetic-secret-token-123456789'

    def json(self):
        raise AssertionError("Error response body must not be parsed")


def test_cloudflare_http_error_does_not_echo_upstream_body(monkeypatch):
    monkeypatch.setenv("FEA_LLM_RETRY_ATTEMPTS", "1")
    monkeypatch.setattr("providers.cloudflare.requests.post", lambda *args, **kwargs: FakeErrorResponse())
    provider = CloudflareProvider("account", "synthetic-account-token", ["test-model"], 100, max_logical_calls=1)
    text, error = provider.chat([{"role": "user", "content": "test"}])
    assert text is None
    assert error == "HTTP 400: upstream error body omitted"
    assert "synthetic-secret-token-123456789" not in error
    assert "Authorization" not in error


def test_openai_compatible_error_helper_redacts_secret_shaped_text():
    provider = OpenAICompatibleProvider("nararouter", "synthetic-key", "test-model", max_retries=1)
    _, error = provider._error("upstream reported sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
    assert "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" not in error
    assert "<redacted-token>" in error
