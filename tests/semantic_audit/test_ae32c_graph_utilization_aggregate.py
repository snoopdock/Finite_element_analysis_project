from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_cli():
    source = Path(__file__).resolve().parents[2] / "tools" / "aggregate_ae32c_graph_utilization.py"
    spec = importlib.util.spec_from_file_location("ae32c_graph_utilization_cli", source)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_cli_aggregates_published_comparison_without_provider_calls(tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    output = tmp_path / "output"
    output.mkdir()
    assessment = {
        "schema_version": "ae32c/graph-utilization-assessment/v1",
        "status": "observed",
        "backend": {
            "active_computation_backend": "networkx",
            "backend_library_version": "3.6.1",
        },
        "graph_query_usage": {
            "attempt_count": 2,
            "successful_call_count": 2,
            "complete_query_count": 2,
            "failed_call_count": 0,
            "mode_counts": {"impact": 1},
        },
        "source_follow_through": {
            "graph_surfaced_unique_path_count": 3,
            "verified_complete_hash_matching_path_count": 2,
            "verified_follow_through_rate": 0.666667,
        },
        "claim_linkage": {
            "claims_citing_graph_tool_evidence_count": 1,
            "claim_count": 2,
        },
        "provider_resource_usage": {
            "provider_reported_tokens": 1200,
            "elapsed_seconds": 10.5,
        },
        "graph_derived_tool_usage": {
            "graph_neighbors": {"attempt_count": 2},
        },
    }
    comparison = {
        "schema_version": "ae32c/evaluation-comparison/v1",
        "evaluation_id": "ae32c-eval-" + "a" * 32,
        "provider": "cloudflare",
        "model": "test-model",
        "source_manifest_sha256": "b" * 64,
        "comparison_metrics": {
            "baseline_reported_tokens": 300,
            "graph_assisted_reported_tokens": 1200,
            "baseline_elapsed_seconds": 2.5,
            "graph_assisted_elapsed_seconds": 10.5,
            "graph_assisted_tool_call_count": 6,
        },
        "graph_assisted": {
            "summary": {"graph_utilization_assessment": {
                "status": "observed",
                "active_computation_backend": "networkx",
            }},
            "report": {"graph_utilization_assessment": assessment},
        },
    }
    input_path = inputs / "comparison.json"
    input_path.write_text(json.dumps(comparison), encoding="utf-8")
    monkeypatch.chdir(checkout)
    cli = _load_cli()
    code = cli.main(["--input", str(input_path), "--output-dir", str(output)])
    assert code == 0
    published = list(output.glob("ae32c-graph-utilization-*"))
    assert len(published) == 1
    report = json.loads((published[0] / "graph_utilization_aggregate.json").read_text(encoding="utf-8"))
    assert report["run_count"] == 1
    assert report["runs"][0]["active_computation_backend"] == "networkx"
    assert report["runs"][0]["graph_verified_follow_through_path_count"] == 2
    assert report["runs"][0]["baseline_reported_tokens"] == 300
    assert report["runs"][0]["graph_assisted_reported_tokens"] == 1200
    assert (published[0] / "graph_utilization_aggregate.md").is_file()
    assert (published[0] / "SHA256SUMS.txt").is_file()


def test_cli_rejects_duplicate_evaluation_ids(tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    output = tmp_path / "output"
    output.mkdir()
    comparison = {
        "schema_version": "ae32c/evaluation-comparison/v1",
        "evaluation_id": "ae32c-eval-" + "c" * 32,
        "provider": "p",
        "model": "m",
        "source_manifest_sha256": "d" * 64,
        "graph_assisted": {"report": {"graph_utilization_assessment": {
            "schema_version": "ae32c/graph-utilization-assessment/v1",
            "backend": {},
            "graph_query_usage": {},
            "source_follow_through": {},
            "claim_linkage": {},
            "provider_resource_usage": {},
            "graph_derived_tool_usage": {},
        }}},
    }
    first = inputs / "one.json"
    second = inputs / "two.json"
    first.write_text(json.dumps(comparison), encoding="utf-8")
    second.write_text(json.dumps(comparison), encoding="utf-8")
    monkeypatch.chdir(checkout)
    cli = _load_cli()
    assert cli.main(["--input", str(first), "--input", str(second), "--output-dir", str(output)]) == 2
    assert list(output.iterdir()) == []


def test_live_evaluation_help_exposes_trusted_graph_backend_selection(capsys):
    import pytest
    from audit_engine.semantic_audit.ae32c.live_evaluation import main

    with pytest.raises(SystemExit) as error:
        main(["--help"])
    assert error.value.code == 0
    output = capsys.readouterr().out
    assert "--graph-backend" in output
    assert "unavailable backends fail closed" in output
