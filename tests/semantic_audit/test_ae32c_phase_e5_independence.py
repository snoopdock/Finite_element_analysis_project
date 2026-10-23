"""E.5 independent-conditions, source witness, and provider-envelope oracles.

All tests are offline; no provider secrets, network requests, or GitHub actions.
"""
from __future__ import annotations

import json
from pathlib import Path

from audit_engine.semantic_audit.ae32c import live_evaluation
from audit_engine.semantic_audit.ae32c.batch_evaluation import evaluate_trial, build_summary
from audit_engine.semantic_audit.ae32c.evaluation import build_comparison_record
from providers.openai_compatible import completion_envelope_diagnostic, OpenAICompatibleProvider
from tests.semantic_audit.test_ae32c_phase_e3_fidelity import _make_trial
from tests.semantic_audit.test_ae32c_phase_e4_support import corpus, scripted, CALLER, ADAPTER
from audit_engine.semantic_audit.ae32c import RepositoryInvestigator, InvestigationLimits
from tests.test_provider_openai_compatible import FakeResponse


def test_baseline_failure_does_not_skip_graph_condition(tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    repo = checkout / "incident"
    repo.mkdir(parents=True)
    (repo / "pipeline").mkdir()
    (repo / "providers").mkdir()
    (repo / "pipeline" / "extractor.py").write_text("def extract(provider):\n  return provider.total_calls\n")
    (repo / "providers" / "adapter.py").write_text("class Adapter:\n  pass\n")
    out = tmp_path / "artifact"
    out.mkdir()
    monkeypatch.chdir(checkout)
    created = []

    class FakeProvider:
        model = "fixed-test-model"
        def chat(self, *a, **kw):
            return None, "synthetic upstream failure"
        def get_stats(self):
            return {"usage": {}, "last_error_code": "malformed_completion_envelope",
                    "last_envelope_diagnostic": {"envelope_kind": "upstream_error_object",
                                                "choices_shape": "absent", "has_error_object": True}}

    def construct_provider(*args, **kwargs):
        created.append((args, kwargs))
        return FakeProvider()

    class FakeInvestigator:
        def __init__(self, *args, **kwargs):
            created.append(("investigator", kwargs))
        def run(self, *args):
            return {"status": "completed", "stop_reason": "diagnosis_submitted",
                    "tool_calls": [], "model_actions": [], "evidence_ledger": []}

    monkeypatch.setattr(live_evaluation, "_build_provider", construct_provider)
    monkeypatch.setattr(live_evaluation, "RepositoryInvestigator", FakeInvestigator)
    status = live_evaluation.main(["--confirm-live-provider-calls", "--provider", "nararouter",
                                   "--repo-root", str(repo), "--output-dir", str(out)])
    assert status == 0
    comparison = next(out.rglob("comparison.json"))
    record = json.loads(comparison.read_text())
    assert record["baseline"]["status"] == "provider_failed"
    assert record["baseline"]["error_code"] == "malformed_completion_envelope"
    assert record["baseline"]["envelope_diagnostic"]["envelope_kind"] == "upstream_error_object"
    assert "synthetic upstream failure" not in repr(record["baseline"]["envelope_diagnostic"])
    assert record["graph_assisted"]["summary"]["status"] == "completed"
    assert len([x for x in created if x[0] != "investigator"]) == 2
    assert any(x[0] == "investigator" for x in created)


def test_batch_tracks_baseline_separately_from_graph_gate(tmp_path):
    root = _make_trial(tmp_path, 1, "nararouter")
    comparison = next(root.rglob("comparison.json"))
    record = json.loads(comparison.read_text())
    record["baseline"]["status"] = "provider_failed"
    comparison.write_text(json.dumps(record, sort_keys=True) + "\n")
    # Recalculate fixture checksum so failure is not an integrity artefact.
    import hashlib
    manifest = comparison.parent / "SHA256SUMS.txt"
    md = comparison.parent / "comparison.md"
    manifest.write_text(hashlib.sha256(comparison.read_bytes()).hexdigest()+"  comparison.json\n"+
                        hashlib.sha256(md.read_bytes()).hexdigest()+"  comparison.md\n")
    result = evaluate_trial(root, round_number=1, provider="nararouter")
    assert result["baseline_complete"] is False
    assert result["graph_protocol_complete"] is True
    assert result["evidence_complete"] is True
    assert result["passed"] is False
    assert result["issues"] == ["baseline_not_completed"]
    # Overall batch fails even though the graph condition independently passed.
    for name in ("cloudflare", "openrouter"):
        _make_trial(tmp_path, 1, name)
    summary = build_summary(tmp_path, 1)
    assert summary["baseline_completed"] == 2
    assert summary["graph_protocol_completed"] == 3
    assert summary["passed"] is False


def test_anchor_guidance_lists_only_observed_source_line_candidates(tmp_path):
    tools = corpus(tmp_path)
    provider = scripted(tools)
    engine = RepositoryInvestigator(tmp_path, provider, evidence_tools=tools,
        required_source_paths=(CALLER, ADAPTER),
        required_source_anchors={CALLER: ("provider.total_calls",), ADAPTER: ("self.calls",)},
        limits=InvestigationLimits(max_rounds=3, finalization_rounds_reserved=1,
            max_total_tokens=90_000, max_total_prompt_chars=190_000),
        id_factory=lambda:"e5-witness-regression")
    report = engine.run("Review the static source")
    assert report["status"] == "completed"
    messages = [json.loads(item["content"]) for batch in provider.messages for item in batch
                if item["role"] == "user" and '"required_source_line_witnesses"' in item["content"]]
    assert messages
    candidates = [entry for m in messages for entry in m.get("required_source_line_witnesses", [])
                  if entry.get("witness_status") == "observed"]
    assert any(entry["anchor"] == "self.calls" and
               any(ref["line"] == 3 for ref in entry["source_reference_candidates"])
               for entry in candidates)
    assert any(entry["anchor"] == "provider.total_calls" for entry in candidates)


def test_envelope_diagnostics_are_allowlisted_and_not_content_leaks():
    diagnostic = completion_envelope_diagnostic({"error":{"message":"secret-error-message"},
        "token":"hidden-token", "id":"sensitive-id", "choices": None})
    assert diagnostic == {"envelope_kind": "upstream_error_object", "choices_shape": "wrong_type", "has_error_object": True}
    assert "secret" not in repr(diagnostic)
    assert completion_envelope_diagnostic({"data": {"reply":"do-not-expose"}})["envelope_kind"] == "alternate_wrapper"
    assert completion_envelope_diagnostic({"choices": [{"message":{"content":"ok"}}]})["envelope_kind"] == "standard_choices"
    assert completion_envelope_diagnostic([])["envelope_kind"] == "non_object"


def test_nararouter_http_200_error_shape_stays_fail_closed(monkeypatch):
    monkeypatch.setattr("providers.openai_compatible.requests.post", lambda *args, **kwargs:
                        FakeResponse(status_code=200, payload={"error": {"message": "sensitive-info"}}))
    provider = OpenAICompatibleProvider("nararouter", "secret-api-key", "agnes-2.5-flash", max_retries=1)
    result, error = provider.chat([{"role": "user", "content": "hello"}])
    stats = provider.get_stats()
    assert result is None and "missing choices" in error
    assert stats["last_error_code"] == "malformed_completion_envelope"
    assert stats["envelope_diagnostic_counts"] == {"upstream_error_object": 1}
    assert stats["last_envelope_diagnostic"]["has_error_object"] is True
    assert "sensitive-info" not in repr(stats)
    assert "secret-api-key" not in repr(stats)
