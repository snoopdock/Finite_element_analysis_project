from __future__ import annotations

import json

from tools import ae32c_provider_compatibility_smoke as smoke


class StructuredSmokeProvider:
    def __init__(self, response: str):
        self.response = response
        self.calls = []
        self.max_retries = 4

    def get_capabilities(self):
        return {"json_object_mode": True}

    def chat(self, messages, temperature=0.0, max_tokens=None, model=None, response_format=None):
        self.calls.append({
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "model": model,
            "response_format": response_format,
        })
        return self.response, None

    def get_stats(self):
        return {
            "logical_calls": len(self.calls),
            "http_attempts": len(self.calls),
            "structured_json_calls": sum(1 for call in self.calls if call["response_format"]),
            "usage": {"total_tokens": 4},
        }


def test_json_object_probe_requests_response_format_once_and_records_only_safe_result(monkeypatch, capsys):
    provider = StructuredSmokeProvider('{"marker":"AE32_SMOKE_OK"}')
    monkeypatch.setenv("NARAROUTER_API_KEY", "test-secret")
    monkeypatch.setenv("FEA_NARAROUTER_JSON_OBJECT_MODE", "1")
    monkeypatch.setattr(smoke, "build_provider", lambda *args, **kwargs: provider)

    result_code = smoke.main([
        "--confirm-live-provider-calls", "--provider", "nararouter",
        "--model", "laguna-s-2.1", "--request-mode", "json_object",
    ])
    output = capsys.readouterr().out
    result = json.loads(output)

    assert result_code == 0
    assert len(provider.calls) == 1
    assert provider.max_retries == 1
    assert provider.calls[0]["response_format"] == {"type": "json_object"}
    assert result["request_mode"] == "json_object"
    assert result["response_format_requested"] is True
    assert result["capability_declared"] is True
    assert result["response_received"] is True
    assert result["response_is_json_object"] is True
    assert result["response_marker_match"] is True
    assert result["logical_calls_reported"] == 1
    assert result["http_attempts_reported"] == 1
    assert result["structured_json_calls"] == 1
    assert "test-secret" not in output
    assert '{"marker":"AE32_SMOKE_OK"}' not in output


def test_json_object_probe_marks_non_json_response_without_logging_it(monkeypatch, capsys):
    private_text = "PRIVATE_RAW_RESPONSE_NOT_TO_BE_LOGGED"
    provider = StructuredSmokeProvider(private_text)
    monkeypatch.setenv("NARAROUTER_API_KEY", "test-secret")
    monkeypatch.setenv("FEA_NARAROUTER_JSON_OBJECT_MODE", "1")
    monkeypatch.setattr(smoke, "build_provider", lambda *args, **kwargs: provider)

    smoke.main([
        "--confirm-live-provider-calls", "--provider", "nararouter",
        "--model", "laguna-s-2.1", "--request-mode", "json_object",
    ])
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result["response_received"] is True
    assert result["response_is_json_object"] is False
    assert result["response_marker_match"] is False
    assert private_text not in output


def test_json_object_probe_requires_explicit_adapter_opt_in(monkeypatch, capsys):
    provider = StructuredSmokeProvider('{"marker":"AE32_SMOKE_OK"}')
    provider.get_capabilities = lambda: {"json_object_mode": False}
    monkeypatch.setenv("NARAROUTER_API_KEY", "test-secret")
    monkeypatch.delenv("FEA_NARAROUTER_JSON_OBJECT_MODE", raising=False)
    monkeypatch.setattr(smoke, "build_provider", lambda *args, **kwargs: provider)

    smoke.main([
        "--confirm-live-provider-calls", "--provider", "nararouter",
        "--model", "laguna-s-2.1", "--request-mode", "json_object",
    ])
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result["status"] == "capability_not_declared"
    assert result["live_provider_calls_made"] is False
    assert provider.calls == []
