"""AE-32D benchmark starter invariants; no provider calls or external dependencies."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "evaluation" / "ae32d"


def test_benchmark_scaffold_is_versioned_and_pending_case_is_not_scoreable():
    case_schema = json.loads((BENCHMARK / "case.schema.json").read_text(encoding="utf-8"))
    manifest_schema = json.loads((BENCHMARK / "manifest.schema.json").read_text(encoding="utf-8"))
    case = json.loads((BENCHMARK / "cases" / "AE32D-CANDIDATE-PROVIDER-INTERFACE-001.json").read_text(encoding="utf-8"))
    manifest = json.loads((BENCHMARK / "manifest.json").read_text(encoding="utf-8"))

    assert case_schema["$schema"].endswith("/2020-12/schema")
    assert case_schema["properties"]["schema_version"]["const"] == "ae32d/case/v1"
    assert manifest_schema["properties"]["schema_version"]["const"] == "ae32d/manifest/v1"
    assert case["schema_version"] == "ae32d/case/v1"
    assert case["ground_truth"]["label"] == "pending_adjudication"
    assert case["review"]["required_independent_reviewers"] >= 2
    assert case["evaluation"]["primary_benchmark_eligible"] is False
    assert manifest["schema_version"] == "ae32d/manifest/v1"
    assert manifest["status"] == "design_only"
    assert manifest["cases"][0]["case_id"] == case["case_id"]
    assert manifest["cases"][0]["primary_benchmark_eligible"] is False


def test_benchmark_protocol_keeps_correctness_separate_from_protocol_completion():
    protocol = (ROOT / "docs" / "audit-engine" / "AE-32D-Audit-Quality-Benchmark-Protocol.md").read_text(encoding="utf-8")
    assert "independently adjudicated audit quality" in protocol
    assert "Baseline + graph" in protocol
    assert "Causal explanation" in protocol
    assert "textual witness is a lexical check only" in protocol.lower()
    assert "two reviewers" in protocol
