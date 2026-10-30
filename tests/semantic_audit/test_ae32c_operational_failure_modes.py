"""Regression tests for observed E.5 live failure modes; no live provider calls."""
from __future__ import annotations

import json

from audit_engine.semantic_audit.ae32c import InvestigationLimits, RepositoryInvestigator
from providers.openai_compatible import OpenAICompatibleProvider, http_error_diagnostic
from tests.semantic_audit.test_ae32c_phase_e4_support import CALLER, ADAPTER, corpus
from tests.test_provider_openai_compatible import FakeResponse


class FinalOnlyProvider:
    provider_name = "fake-provider"
    model = "fixture-model"

    def __init__(self, response):
        self.response = response
        self.messages = []
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "reported_cost_usd": 0.0}

    def chat(self, messages, temperature=0.0, max_tokens=None, model=None):
        self.messages.append([dict(message) for message in messages])
        return self.response, None

    def get_stats(self):
        return {"provider": self.provider_name, "model": self.model, "usage": dict(self.usage)}


def _final_with_unbound_source_ids(tools):
    caller_hash = tools.file_hashes[CALLER]
    adapter_hash = tools.file_hashes[ADAPTER]
    refs = [
        {"evidence_id": "E9998", "path": CALLER, "line": 2, "source_sha256": caller_hash},
        {"evidence_id": "E9999", "path": ADAPTER, "line": 3, "source_sha256": adapter_hash},
    ]
    diagnosis = {
        "summary": "Static source evidence suggests a possible interface mismatch; runtime causality is not independently established.",
        "root_cause": {
            "statement": "The caller accesses provider.total_calls while the adapter source exposes self.calls; inspect the intended contract before changing code.",
            "confidence": "medium",
            "evidence_refs": [],
            "source_references": refs,
        },
        "claims": [{
            "statement": "The exact caller and adapter source lines were read from the indexed snapshot.",
            "kind": "observation",
            "confidence": "high",
            "evidence_refs": [],
            "source_references": refs,
        }],
        "proposed_corrective_action": "Verify the public provider interface and tests before proposing a fix.",
        "limitations": ["Static text does not prove runtime object identity or dynamic behavior."],
        "next_steps": ["Inspect the caller contract and reproduce the failure in a controlled test."],
    }
    return json.dumps({"action": "final", "diagnosis": diagnosis})


def test_required_source_paths_are_prefetched_before_first_model_turn(tmp_path):
    tools = corpus(tmp_path)
    provider = FinalOnlyProvider(_final_with_unbound_source_ids(tools))
    engine = RepositoryInvestigator(
        tmp_path,
        provider,
        evidence_tools=tools,
        required_source_paths=(CALLER, ADAPTER),
        required_source_anchors={CALLER: ("provider.total_calls",), ADAPTER: ("self.calls",)},
        limits=InvestigationLimits(max_rounds=4, finalization_rounds_reserved=1,
            max_tool_calls=12, max_total_tokens=90_000, max_total_prompt_chars=190_000),
        id_factory=lambda: "test-required-source-prefetch",
    )
    report = engine.run("Inspect the declared provider interface incident")

    assert [call["tool"] for call in report["tool_calls"][:3]] == ["repository_summary", "read_source_file", "read_source_file"]
    first_user_payload = json.loads(provider.messages[0][1]["content"])
    preloaded = first_user_payload["required_source_evidence"]
    assert [item["evidence_id"] for item in preloaded] == ["E0002", "E0003"]
    assert all(item["response"]["source_range_complete"] is True for item in preloaded)
    assert report["required_source_coverage"]["status"] == "complete"
    assert report["source_textual_support"]["status"] == "complete"
    assert report["diagnosis"] is not None
    assert {ref["evidence_id"] for ref in report["diagnosis"]["root_cause"]["source_references"]} == {"E0002", "E0003"}
    assert sum(event.get("event") == "source_reference_binding_repaired" for event in report["errors"]) >= 2


def test_http_400_diagnostic_keeps_safe_code_and_drops_free_text(monkeypatch):
    monkeypatch.setattr(
        "providers.openai_compatible.requests.post",
        lambda *args, **kwargs: FakeResponse(status_code=400, payload={
            "error": {
                "type": "invalid_request_error",
                "code": "model_not_found",
                "param": "model",
                "message": "private diagnostic text must not be stored",
                "api_key": "secret-must-not-leak",
            },
            "token": "another-secret",
        }),
    )
    provider = OpenAICompatibleProvider("nararouter", "secret-api-key", "agnes-2.5-flash", max_retries=1)
    response, error = provider.chat([{"role": "user", "content": "hello"}])
    stats = provider.get_stats()

    assert response is None
    assert "HTTP 400" in error
    diagnostic = stats["last_http_error_diagnostic"]
    assert diagnostic["http_status"] == 400
    assert diagnostic["error_type"] == "invalid_request_error"
    assert diagnostic["error_code"] == "model_not_found"
    assert diagnostic["error_param"] == "model"
    serialized = json.dumps(stats)
    assert "private diagnostic text" not in serialized
    assert "secret-must-not-leak" not in serialized
    assert "another-secret" not in serialized
    assert "secret-api-key" not in serialized


def test_http_error_diagnostic_never_copies_arbitrary_values():
    diagnostic = http_error_diagnostic({
        "error": {"type": "bad type with spaces", "code": "code/allowed", "message": "do-not-copy"},
        "api_key": "do-not-copy-either",
    }, 400)
    assert diagnostic["error_type"] == "present_unclassified"
    assert diagnostic["error_code"] == "code/allowed"
    assert "message" in diagnostic["error_fields"]
    assert "do-not-copy" not in repr(diagnostic)
    assert "api_key" not in repr(diagnostic)


def test_investigator_report_exposes_only_allowlisted_http_diagnostics(tmp_path):
    tools = corpus(tmp_path)

    class DiagnosticProvider(FinalOnlyProvider):
        def get_stats(self):
            return {
                "provider": "nararouter",
                "model": "fixture-model",
                "usage": {},
                "last_error_code": "provider_api_error_payload",
                "last_http_status": 400,
                "last_envelope_diagnostic": {
                    "envelope_kind": "upstream_error_object",
                    "choices_shape": "absent",
                    "has_error_object": True,
                    "message": "must-not-be-copied",
                },
                "last_http_error_diagnostic": {
                    "http_status": 400,
                    "body_status": "json",
                    "body_shape": "object",
                    "error_shape": "object",
                    "error_type": "invalid_request_error",
                    "error_code": "model_not_found",
                    "error_param": "model",
                    "error_message_category": "provider_internal_error",
                    "error_request_id": "req-12345",
                    "error_fields": ["type", "code", "param", "message"],
                    "top_level_error_fields": [],
                    "message": "must-not-be-copied",
                    "api_key": "must-not-be-copied-either",
                },
            }

    provider = DiagnosticProvider("{}")
    engine = RepositoryInvestigator(tmp_path, provider, evidence_tools=tools)
    report = engine._finalize_report(engine._base_report("safe diagnostics"), "incomplete", "provider_failure")
    safe = report["provider"]["last_http_error_diagnostic"]
    assert report["provider"]["last_http_status"] == 400
    assert report["provider"]["last_envelope_kind"] == "upstream_error_object"
    assert report["provider"]["last_envelope_diagnostic"] == {
        "envelope_kind": "upstream_error_object",
        "choices_shape": "absent",
        "has_error_object": True,
    }
    assert safe["error_code"] == "model_not_found"
    assert safe["error_message_category"] == "provider_internal_error"
    assert safe["error_request_id"] == "req-12345"
    assert "message" not in safe
    assert "api_key" not in safe


def test_required_source_prefetch_does_not_swallow_provenance_mismatch(tmp_path):
    tools = corpus(tmp_path)
    original_invoke = tools.invoke

    def altered_invoke(tool, arguments):
        response = original_invoke(tool, arguments)
        if tool == "read_source_file":
            response = dict(response)
            provenance = dict(response.get("provenance", {}))
            provenance["graph_fingerprint"] = "f" * 64
            response["provenance"] = provenance
        return response

    tools.invoke = altered_invoke
    provider = FinalOnlyProvider("{}")
    engine = RepositoryInvestigator(
        tmp_path,
        provider,
        evidence_tools=tools,
        required_source_paths=(CALLER, ADAPTER),
        required_source_anchors={CALLER: ("provider.total_calls",), ADAPTER: ("self.calls",)},
        limits=InvestigationLimits(max_rounds=4, finalization_rounds_reserved=1,
            max_tool_calls=12, max_total_tokens=90_000, max_total_prompt_chars=190_000),
        id_factory=lambda: "test-prefetch-provenance-fail-closed",
    )
    report = engine.run("Check the source snapshot")
    assert report["status"] == "incomplete"
    assert report["stop_reason"] == "evidence_provenance_mismatch"
    assert provider.messages == []


def test_provider_smoke_makes_one_call_and_never_prints_raw_response(monkeypatch, capsys):
    from tools import ae32c_provider_compatibility_smoke as smoke

    class SmokeProvider:
        def __init__(self):
            self.calls = 0
            self.max_retries = 3
        def chat(self, messages, temperature=0.0, max_tokens=None, model=None):
            self.calls += 1
            assert max_tokens == 128
            return "private model output must not be printed", None
        def get_stats(self):
            return {"logical_calls": self.calls, "usage": {"total_tokens": 12}}

    provider = SmokeProvider()
    monkeypatch.setenv("NARAROUTER_API_KEY", "test-secret")
    monkeypatch.setattr(smoke, "build_provider", lambda *args, **kwargs: provider)
    exit_code = smoke.main(["--confirm-live-provider-calls", "--provider", "nararouter"])
    output = capsys.readouterr().out
    result = json.loads(output)

    assert exit_code == 0
    assert provider.calls == 1
    assert provider.max_retries == 1
    assert result["http_attempts_reported"] == 1
    assert result["status"] == "completion_received"
    assert result["logical_calls_reported"] == 1
    assert result["response_marker_match"] is False
    assert "private model output" not in output
    assert "test-secret" not in output


def test_provider_smoke_requires_explicit_consent(monkeypatch):
    from tools import ae32c_provider_compatibility_smoke as smoke
    called = []
    monkeypatch.setattr(smoke, "build_provider", lambda *args, **kwargs: called.append(True))
    import pytest
    with pytest.raises(SystemExit) as exc:
        smoke.main(["--provider", "nararouter"])
    assert exc.value.code == 2
    assert called == []
