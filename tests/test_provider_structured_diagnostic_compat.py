"""Offline compatibility checks for diagnostic + structured JSON adapter behavior."""
from __future__ import annotations

import json

import pytest

from providers.openai_compatible import OpenAICompatibleProvider, http_error_diagnostic
from tests.test_provider_openai_compatible import FakeResponse, success_payload


def test_restored_diagnostic_rejects_untrusted_values():
    secret = "provider-private-value-never-persist"
    result = http_error_diagnostic({
        "error": {
            "type": "invalid_request_error",
            "code": "model_not_found",
            "param": "model",
            "message": "The model is not found; " + secret,
            "api_key": secret,
            "request_id": "req-safe_123",
        },
        "api_key": secret,
    }, 400)
    assert result["http_status"] == 400
    assert result["error_code"] == "model_not_found"
    assert result["error_type"] == "invalid_request_error"
    assert result["error_param"] == "model"
    assert result["error_request_id"] == "req-safe_123"
    assert result["error_message_category"] == "model_identifier_rejected"
    assert "message" in result["error_fields"]
    assert secret not in json.dumps(result)
    assert "api_key" not in json.dumps(result)


def test_http_error_statistics_preserved_with_structured_mode_enabled(monkeypatch):
    model = "nvidia/nemotron-3.5-super-vl:free"
    captured = {}
    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return FakeResponse(status_code=400, payload={
            "error": {"code": "unsupported_response_format", "type": "invalid_request_error",
                      "param": "response_format", "message": "Unsupported parameter: response_format"},
            "token": "never-copy-this-token",
        })
    monkeypatch.setattr("providers.openai_compatible.requests.post", fake_post)
    provider = OpenAICompatibleProvider("openrouter", "private-api-key", model, max_retries=1)
    assert provider.get_capabilities()["json_object_mode"] is True
    response, error = provider.chat_structured([{"role": "user", "content": "return JSON"}])
    assert response is None and "HTTP 400" in error
    assert captured["json"]["response_format"] == {"type": "json_object"}
    assert captured["json"]["provider"] == {"require_parameters": True}
    stats = provider.get_stats()
    assert stats["structured_json_calls"] == 1
    assert stats["last_http_error_diagnostic"]["error_code"] == "unsupported_response_format"
    assert stats["last_http_error_diagnostic"]["error_message_category"] == "request_parameter_rejected"
    assert stats["http_error_diagnostic_counts"]["unsupported_response_format"] == 1
    assert "private-api-key" not in json.dumps(stats)
    assert "never-copy-this-token" not in json.dumps(stats)
    assert "Unsupported parameter: response_format" not in json.dumps(stats)


def test_http_error_diagnostic_is_reset_on_next_request(monkeypatch):
    responses = [
        FakeResponse(status_code=400, payload={"error": {"type": "bad_request", "code": "bad_model"}}),
        FakeResponse(payload=success_payload()),
    ]
    monkeypatch.setattr("providers.openai_compatible.requests.post", lambda *args, **kwargs: responses.pop(0))
    provider = OpenAICompatibleProvider("nararouter", "private-key", "laguna-s-2.1", max_retries=1)
    assert provider.chat([{"role": "user", "content": "first"}])[0] is None
    assert provider.get_stats()["last_http_error_diagnostic"]["http_status"] == 400
    assert provider.chat([{"role": "user", "content": "second"}])[0] == "ok"
    assert provider.get_stats()["last_http_error_diagnostic"] is None
    assert provider.get_stats()["http_error_diagnostic_counts"]["bad_model"] == 1
    assert provider.get_stats()["structured_json_calls"] == 0


def test_nararouter_json_mode_remains_disabled_by_default(monkeypatch):
    monkeypatch.delenv("FEA_NARAROUTER_JSON_OBJECT_MODE", raising=False)
    provider = OpenAICompatibleProvider("nararouter", "private-key", "laguna-s-2.1")
    assert provider.get_capabilities()["json_object_mode"] is False


def test_response_too_large_diagnostic_is_allowlisted(monkeypatch):
    from providers.response_limits import ProviderResponseTooLarge
    monkeypatch.setattr("providers.openai_compatible.requests.post", lambda *a, **kw: FakeResponse(status_code=400))
    monkeypatch.setattr("providers.openai_compatible.load_bounded_json", lambda *a, **kw: (_ for _ in ()).throw(ProviderResponseTooLarge("body too large")))
    provider = OpenAICompatibleProvider("openrouter", "private-key", "nvidia/nemotron-3.5-super-vl:free", max_retries=1)
    response, error = provider.chat([{"role": "user", "content": "first"}])
    assert response is None
    assert "HTTP 400" in error
    diagnostic = provider.get_stats()["last_http_error_diagnostic"]
    assert diagnostic == {"http_status": 400, "body_status": "too_large", "body_shape": "non_object"}
