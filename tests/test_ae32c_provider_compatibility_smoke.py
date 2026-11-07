from __future__ import annotations

import json

from tools import ae32c_provider_compatibility_smoke as smoke


VALID_ACTION = {
    "action": "final",
    "diagnosis": {
        "summary": "Synthetic protocol probe.",
        "root_cause": {
            "statement": "No repository diagnosis was performed.",
            "confidence": "low",
            "evidence_refs": ["E0001"],
            "source_references": [],
        },
        "claims": [{
            "statement": "The output follows the requested final-action shape.",
            "kind": "limitation",
            "confidence": "low",
            "evidence_refs": ["E0001"],
            "source_references": [],
        }],
        "proposed_corrective_action": "No corrective action; this was a format probe.",
        "limitations": ["No repository evidence was examined."],
        "next_steps": ["Run a real investigation only after protocol compatibility is established."],
    },
}


class StructuredSmokeProvider:
    def __init__(self, response: str, *, capability: bool = True):
        self.response = response
        self.capability = capability
        self.calls = []
        self.max_retries = 4

    def get_capabilities(self):
        return {"json_object_mode": self.capability}

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


def _setup(monkeypatch, provider):
    monkeypatch.setenv("NARAROUTER_API_KEY", "test-secret")
    monkeypatch.setenv("FEA_NARAROUTER_JSON_OBJECT_MODE", "1")
    monkeypatch.setattr(smoke, "build_provider", lambda *args, **kwargs: provider)


def test_json_object_marker_probe_requests_response_format_once(monkeypatch, capsys):
    provider = StructuredSmokeProvider('{"marker":"AE32_SMOKE_OK"}')
    _setup(monkeypatch, provider)

    result_code = smoke.main([
        "--confirm-live-provider-calls", "--provider", "nararouter",
        "--model", "laguna-s-2.1", "--request-mode", "json_object",
    ])
    result = json.loads(capsys.readouterr().out)

    assert result_code == 0
    assert len(provider.calls) == 1
    assert provider.max_retries == 1
    assert provider.calls[0]["response_format"] == {"type": "json_object"}
    assert result["request_profile"] == "marker"
    assert result["response_is_json_object"] is True
    assert result["response_marker_match"] is True
    assert result["structured_json_calls"] == 1


def test_action_schema_profile_requests_one_structured_call_and_validates_shape(monkeypatch, capsys):
    private_response = json.dumps(VALID_ACTION)
    provider = StructuredSmokeProvider(private_response)
    _setup(monkeypatch, provider)

    result_code = smoke.main([
        "--confirm-live-provider-calls", "--provider", "nararouter",
        "--model", "laguna-s-2.1", "--request-mode", "json_object",
        "--request-profile", "ae32c_final_action",
    ])
    output = capsys.readouterr().out
    result = json.loads(output)

    assert result_code == 0
    assert len(provider.calls) == 1
    assert provider.calls[0]["response_format"] == {"type": "json_object"}
    assert provider.calls[0]["max_tokens"] == 768
    assert result["status"] == "action_schema_shape_valid"
    assert result["json_parse_success"] is True
    assert result["schema_shape_valid"] is True
    assert result["top_level_keys_exact"] is True
    assert result["diagnosis_keys_exact"] is True
    assert result["root_cause_keys_exact"] is True
    assert result["claim_shapes_valid"] is True
    assert result["required_value_types_valid"] is True
    assert result["semantic_evidence_validation_performed"] is False
    assert result["source_reference_resolution_performed"] is False
    assert result["structured_json_calls"] == 1
    assert private_response not in output
    assert "test-secret" not in output


def test_action_schema_profile_distinguishes_valid_json_from_wrong_shape(monkeypatch, capsys):
    provider = StructuredSmokeProvider(json.dumps({"action": "final", "diagnosis": {"summary": "missing required fields"}}))
    _setup(monkeypatch, provider)

    smoke.main([
        "--confirm-live-provider-calls", "--provider", "nararouter",
        "--model", "laguna-s-2.1", "--request-mode", "json_object",
        "--request-profile", "ae32c_final_action",
    ])
    result = json.loads(capsys.readouterr().out)

    assert result["json_parse_success"] is True
    assert result["response_is_json_object"] is True
    assert result["schema_shape_valid"] is False
    assert "diagnosis_keys_invalid" in result["schema_errors"]
    assert result["status"] == "action_schema_shape_invalid"


def test_action_schema_profile_reports_syntax_location_without_raw_response(monkeypatch, capsys):
    private_response = "PRIVATE_NOT_JSON_RESPONSE"
    provider = StructuredSmokeProvider(private_response)
    _setup(monkeypatch, provider)

    smoke.main([
        "--confirm-live-provider-calls", "--provider", "nararouter",
        "--model", "laguna-s-2.1", "--request-mode", "json_object",
        "--request-profile", "ae32c_final_action",
    ])
    output = capsys.readouterr().out
    result = json.loads(output)

    assert result["json_parse_success"] is False
    assert result["json_error_category"] == "invalid_json_syntax"
    assert result["json_error_line"] >= 1
    assert result["json_error_column"] >= 1
    assert result["schema_shape_valid"] is False
    assert private_response not in output


def test_json_object_probe_requires_explicit_adapter_opt_in(monkeypatch, capsys):
    provider = StructuredSmokeProvider(json.dumps(VALID_ACTION), capability=False)
    _setup(monkeypatch, provider)
    monkeypatch.delenv("FEA_NARAROUTER_JSON_OBJECT_MODE", raising=False)

    smoke.main([
        "--confirm-live-provider-calls", "--provider", "nararouter",
        "--model", "laguna-s-2.1", "--request-mode", "json_object",
        "--request-profile", "ae32c_final_action",
    ])
    result = json.loads(capsys.readouterr().out)

    assert result["status"] == "capability_not_declared"
    assert result["live_provider_calls_made"] is False
    assert result["request_profile"] == "ae32c_final_action"
    assert provider.calls == []
