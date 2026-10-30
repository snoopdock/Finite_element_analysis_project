"""E.4 independent test oracles: literal source-line support and batch integrity.

These tests do not claim to prove missing Python attributes or runtime failures.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from audit_engine.semantic_audit.ae32c import InvestigationLimits, RepositoryInvestigator
from audit_engine.semantic_audit.ae32c.batch_evaluation import evaluate_trial, build_summary
from audit_engine.semantic_audit.ae32b.evidence_tools import RepositoryEvidenceTools
from tests.semantic_audit.test_ae32c_phase_e1_reliability import FakeProvider, action_tool
from tests.semantic_audit.test_ae32c_phase_e3_fidelity import _make_trial

CALLER = "pipeline/extractor.py"
ADAPTER = "providers/adapter.py"


def corpus(root: Path):
    for parent in (root / "pipeline", root / "providers"):
        parent.mkdir()
    (root / CALLER).write_text('def extract(provider):\n    return provider.total_calls\n', encoding="utf-8")
    (root / ADAPTER).write_text('class Adapter:\n    def __init__(self):\n        self.calls = 0\n', encoding="utf-8")
    tools = RepositoryEvidenceTools(root)
    return tools


def scripted(tools, *, confidence="high", cited_line=3, cite_search=False):
    a, b = tools.file_hashes[CALLER], tools.file_hashes[ADAPTER]
    refs = [{"evidence_id": "E0002", "path": CALLER, "line": 2, "source_sha256": a},
            {"evidence_id": "E0003", "path": ADAPTER, "line": cited_line, "source_sha256": b}]
    diag = {"summary": "Static attribute observations only", "root_cause": {
        "statement": "The reader and adapter use different attribute spellings; runtime behavior not reproduced",
        "confidence": confidence, "evidence_refs": ["E0002", "E0003"], "source_references": refs},
        "claims": [{"statement": "Source lines were read", "kind": "observation", "confidence": "medium",
                    "evidence_refs": ["E0002", "E0003"], "source_references": refs}],
        "proposed_corrective_action": "Review the interface", "limitations": ["No runtime experiment"],
        "next_steps": ["Run an isolated reproduction"]}
    final_response = json.dumps({"action":"final","diagnosis":diag})
    outputs = [action_tool("read_source_file", {"path": CALLER, "start_line": 1, "end_line": 20}),
               action_tool("read_source_file", {"path": ADAPTER, "start_line": 1, "end_line": 20}),
               final_response,
               final_response]
    return FakeProvider(outputs)


def run(root: Path, *, confidence="high", cited_line=3):
    tools = corpus(root)
    provider = scripted(tools, confidence=confidence, cited_line=cited_line)
    engine = RepositoryInvestigator(root, provider, evidence_tools=tools,
        required_source_paths=(CALLER, ADAPTER),
        required_source_anchors={CALLER: ("provider.total_calls",), ADAPTER: ("self.calls",)},
        limits=InvestigationLimits(max_rounds=4, finalization_rounds_reserved=1,
            max_total_tokens=90_000, max_total_prompt_chars=190_000),
        id_factory=lambda:"e4-support-regression")
    return engine.run("Evaluate the source attributes, without asserting runtime proof"), provider


def test_code_line_witnesses_cited_from_exact_full_source_reads(tmp_path):
    report, provider = run(tmp_path)
    assert report["diagnosis"] is not None, report
    support = report["source_textual_support"]
    assert support["status"] == "complete", support
    assert len(support["direct_cited_anchors"]) == 2
    assert support["causal_accuracy"] == "requires_independent_review"
    assert report["required_source_coverage"]["status"] == "complete"
    assert report["diagnosis"]["root_cause"]["confidence"] == "high"
    assert any("required_source_textual_anchors" in item[1] for batch in provider.messages for item in
               [(m["role"], m["content"]) for m in batch])


def test_class_line_not_evidence_for_attribute_even_with_valid_citation(tmp_path):
    report, _ = run(tmp_path, confidence="high", cited_line=1)
    assert report["diagnosis"] is None
    assert report["source_textual_support"]["status"] == "incomplete"
    assert any("high_confidence_direct_source_anchor_support_incomplete" in e.get("reason_codes", []) for e in report["errors"])


def test_medium_confidence_does_not_convert_unsupported_line_to_complete(tmp_path):
    report, _ = run(tmp_path, confidence="medium", cited_line=1)
    assert report["status"] == "completed_with_incomplete_evidence", report
    assert report["stop_reason"] == "diagnosis_submitted_with_textual_source_support_gap"
    assert report["source_textual_support"]["missing_direct_cited_anchors"] == [
        {"path": ADAPTER, "anchor": "self.calls"}]


@pytest.mark.parametrize("invalid", [
    {CALLER:("invalid\nname",)},
    {CALLER:("a",)},
    {"../private.py":("hidden",)},
    {ADAPTER:("token",)*5},
])
def test_source_anchor_policy_refuses_invalid_configurations(tmp_path, invalid):
    tools = corpus(tmp_path)
    with pytest.raises(ValueError):
        RepositoryInvestigator(tmp_path, FakeProvider([]), evidence_tools=tools,
            required_source_paths=(CALLER, ADAPTER), required_source_anchors=invalid)


def test_batch_refuses_a_tampered_comparison_even_when_status_looks_passed(tmp_path):
    path = _make_trial(tmp_path, 1, "openrouter")
    evaluation = next(path.rglob("comparison.json"))
    payload = json.loads(evaluation.read_text())
    payload["graph_assisted"]["summary"]["status"] = "completed_with_incomplete_evidence"
    evaluation.write_text(json.dumps(payload), encoding="utf-8")
    row = evaluate_trial(path, round_number=1, provider="openrouter")
    assert "comparison_sha256_manifest_invalid" in row["issues"]
    assert not row["passed"]
    assert row["protocol_complete"] is False


def test_per_provider_batch_denominators_include_failed_trials(tmp_path):
    for provider in ("cloudflare", "nararouter", "openrouter"):
        _make_trial(tmp_path, 1, provider, exit_code=1 if provider == "cloudflare" else 0)
    report = build_summary(tmp_path, 1)
    assert report["provider_breakdown"]["cloudflare"]["trials"] == 1
    assert report["provider_breakdown"]["cloudflare"]["evidence_complete"] == 0
    assert report["provider_breakdown"]["openrouter"]["evidence_complete"] == 1
    assert report["diagnostic_accuracy"] == "not_assessed"

@pytest.mark.parametrize("provider_name,expected", [
    ("cloudflare", "minimal_strict_final_object"),
    ("nararouter", "explicit_action_envelope"),
    ("openrouter", "compact_evidence_bound_final"),
])
def test_provider_specific_guidance_never_changes_required_schema(tmp_path, provider_name, expected):
    tools = corpus(tmp_path)
    scripted_provider = scripted(tools)
    investigator = RepositoryInvestigator(tmp_path, scripted_provider, provider_name=provider_name,
        evidence_tools=tools, limits=InvestigationLimits(max_rounds=4, finalization_rounds_reserved=1),
        required_source_paths=(CALLER, ADAPTER),
        required_source_anchors={CALLER: ("provider.total_calls",), ADAPTER: ("self.calls",)})
    guidance = investigator._provider_protocol_guidance()
    assert guidance["strategy"] == expected
    assert guidance["scope"] == "prompt_only_no_claim_of_provider_schema_enforcement"
    assert guidance["required_top_level_keys"] == ["action", "diagnosis"]
    assert "source_references" in guidance["required_claim_keys"]
