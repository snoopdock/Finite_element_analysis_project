from __future__ import annotations

from types import SimpleNamespace

from audit_engine.semantic_audit.ae32c.evaluation import build_comparison_record, render_comparison_markdown
from audit_engine.semantic_audit.ae32c.graph_utilization import (
    aggregate_graph_utilization_runs,
    build_graph_utilization_assessment,
    summarize_graph_utilization_assessment,
)


def _entry(evidence_id, tool, arguments=None, result=None, status="ok"):
    response = {"status": status, "tool": tool}
    if result is not None:
        response["result"] = result
    return SimpleNamespace(
        evidence_id=evidence_id,
        tool=tool,
        arguments=arguments or {},
        status=status,
        response=response,
    )


def _complete_read(path, digest):
    return {
        "path": path,
        "source_sha256": digest,
        "source_range_complete": True,
        "content_omitted": False,
        "requested_start_line": 1,
        "requested_end_line": 4,
        "start_line": 1,
        "end_line": 4,
        "total_lines": 4,
        "truncated": False,
        "end_clamped_to_eof": False,
    }


def test_graph_utilization_measures_queries_follow_through_claim_linkage_and_cost():
    hash_a = "a" * 64
    hash_b = "b" * 64
    graph_result = {
        "coverage_status": "complete_for_query",
        "truncated": False,
        "source_paths": ["src/a.py", "src/b.py"],
        "source_nodes": [
            {"node_id": "file:src/a.py", "path": "src/a.py", "source_sha256": hash_a},
            {"node_id": "file:src/b.py", "path": "src/b.py", "source_sha256": hash_b},
        ],
        "observed_relation_types": ["CALLS", "IMPORTS"],
        "evidence": [
            {"evidence_id": "GE01", "provenance": {"edge_metadata": {
                "path": "src/b.py", "source_sha256": hash_b,
            }}},
        ],
    }
    ledger = [
        _entry("E0001", "repository_summary", result={"graph_node_count": 2}),
        _entry("E0002", "read_source_file", {"path": "src/a.py"}, _complete_read("src/a.py", hash_a)),
        _entry("E0003", "graph_neighbors", {"node": "symbol:src.a::run", "direction": "impact"}, graph_result),
        _entry("E0004", "read_source_file", {"path": "src/b.py"}, _complete_read("src/b.py", hash_b)),
        _entry("E0005", "graph_path", {"source": "file:src/a.py", "target": "file:src/b.py"}, status="error"),
        _entry("E0006", "find_related_tests", {"target": "src/a.py"}, {"tests": []}),
    ]
    claims = {
        "items": [
            {"claim_id": "C1", "evidence_refs": ["E0003", "E0004"]},
            {"claim_id": "C2", "evidence_refs": ["E0004"]},
        ],
    }
    runtime = {
        "graph_engine": {
            "active_computation_backend": "networkx",
            "backend_library_version": "3.6.1",
            "backend_parity_mode": "strict_per_query_reference_comparison",
            "external_backend_adapters_active": ["networkx"],
            "backend_pipeline_wired_into_ae32b_query_path": True,
            "backend_execution": {
                "queries_attempted": 3,
                "queries_succeeded": 3,
                "queries_failed": 0,
                "parity_verified_queries": 3,
                "parity_failures": 0,
                "total_examined_edges": 20,
                "total_visited_nodes": 8,
            },
        },
    }
    assessment = build_graph_utilization_assessment(
        ledger_entries=ledger,
        graph_tools_enabled=True,
        graph_derived_tools_enabled=True,
        claim_evidence_assessment=claims,
        runtime_architecture=runtime,
        budget={
            "model_rounds_used": 4,
            "provider_requests_attempted": 4,
            "provider_reported_tokens": 1800,
            "total_prompt_chars": 5000,
            "elapsed_seconds": 12.5,
            "provider_reported_cost_usd": 0.003,
        },
    )
    assert assessment["status"] == "observed"
    assert assessment["graph_query_usage"]["attempt_count"] == 2
    assert assessment["graph_query_usage"]["successful_call_count"] == 1
    assert assessment["graph_query_usage"]["complete_query_count"] == 1
    assert assessment["graph_query_usage"]["failed_call_count"] == 1
    assert assessment["graph_query_usage"]["mode_counts"] == {"impact": 1, "graph_path": 1}
    assert assessment["graph_query_usage"]["observed_relation_types"] == ["CALLS", "IMPORTS"]
    follow = assessment["source_follow_through"]
    assert follow["paths_already_read_before_graph_surfacing"] == ["src/a.py"]
    assert follow["eligible_newly_surfaced_path_count"] == 1
    assert follow["verified_paths"] == ["src/b.py"]
    assert follow["verified_follow_through_rate"] == 1.0
    assert assessment["claim_linkage"]["claims_citing_graph_tool_evidence_count"] == 1
    assert assessment["claim_linkage"]["graph_tool_evidence_ids_cited"] == ["E0003"]
    assert assessment["backend"]["active_computation_backend"] == "networkx"
    assert assessment["backend"]["parity_verified_queries"] == 3
    assert assessment["provider_resource_usage"]["reported_tokens_per_graph_query"] == 900.0


def test_partial_or_truncated_graph_result_does_not_create_verified_follow_through():
    digest = "c" * 64
    ledger = [
        _entry("E0001", "graph_neighbors", {"node": "file:src/a.py"}, {
            "coverage_status": "partial",
            "truncated": True,
            "source_paths": ["src/b.py"],
            "source_nodes": [{"path": "src/b.py", "source_sha256": digest}],
        }),
        _entry("E0002", "read_source_file", {"path": "src/b.py"}, _complete_read("src/b.py", digest)),
    ]
    result = build_graph_utilization_assessment(
        ledger_entries=ledger,
        graph_tools_enabled=True,
        graph_derived_tools_enabled=True,
    )
    assert result["graph_query_usage"]["partial_or_truncated_query_count"] == 1
    assert result["source_follow_through"]["graph_surfaced_unique_path_count"] == 0
    assert result["source_follow_through"]["verified_complete_hash_matching_path_count"] == 0


def test_incomplete_read_and_hash_mismatch_are_not_verified():
    expected = "d" * 64
    wrong = "e" * 64
    read = _complete_read("src/b.py", wrong)
    ledger = [
        _entry("E0001", "graph_neighbors", {"node": "file:src/a.py"}, {
            "coverage_status": "complete_for_query",
            "truncated": False,
            "source_paths": ["src/b.py"],
            "source_nodes": [{"path": "src/b.py", "source_sha256": expected}],
        }),
        _entry("E0002", "read_source_file", {"path": "src/b.py"}, read),
    ]
    result = build_graph_utilization_assessment(
        ledger_entries=ledger,
        graph_tools_enabled=True,
        graph_derived_tools_enabled=True,
    )
    assert result["source_follow_through"]["hash_mismatch_path_count"] == 1
    assert result["source_follow_through"]["verified_complete_hash_matching_path_count"] == 0


def test_graph_disabled_and_policy_violation_states_are_explicit():
    disabled = build_graph_utilization_assessment(
        ledger_entries=[],
        graph_tools_enabled=False,
        graph_derived_tools_enabled=False,
    )
    assert disabled["status"] == "not_available_by_design"
    violation = build_graph_utilization_assessment(
        ledger_entries=[_entry("E0001", "graph_neighbors", {"node": "file:x"}, {
            "coverage_status": "complete_for_query", "truncated": False,
        })],
        graph_tools_enabled=False,
        graph_derived_tools_enabled=False,
    )
    assert violation["status"] == "policy_violation_observed"


def test_summary_is_compact_and_aggregate_groups_by_snapshot_and_backend():
    assessment = build_graph_utilization_assessment(
        ledger_entries=[],
        graph_tools_enabled=True,
        graph_derived_tools_enabled=True,
        runtime_architecture={"graph_engine": {"active_computation_backend": "scipy"}},
    )
    summary = summarize_graph_utilization_assessment(assessment)
    assert summary["active_computation_backend"] == "scipy"
    runs = [
        {"provider": "p", "model": "m", "source_manifest_sha256": "a" * 64,
         **summary, "graph_query_attempt_count": 2},
        {"provider": "p", "model": "m", "source_manifest_sha256": "a" * 64,
         **summary, "graph_query_attempt_count": 4},
        {"provider": "p", "model": "m", "source_manifest_sha256": "b" * 64,
         **summary, "graph_query_attempt_count": 1},
    ]
    aggregate = aggregate_graph_utilization_runs(runs)
    assert aggregate["run_count"] == 3
    assert aggregate["group_count"] == 2
    same_snapshot = next(item for item in aggregate["groups"] if item["source_manifest_sha256"] == "a" * 64)
    assert same_snapshot["sample_count"] == 2
    assert same_snapshot["metrics"]["graph_query_attempt_count"]["mean"] == 3.0


def test_comparison_record_surfaces_graph_utilization_and_keeps_accuracy_unassessed():
    graph_report = {
        "status": "completed",
        "stop_reason": "final_diagnosis_accepted",
        "tool_calls": [],
        "evidence_ledger": [],
        "model_actions": [],
        "budget": {
            "model_rounds_used": 3,
            "provider_reported_tokens": 900,
        },
        "graph_utilization_assessment": {
            "schema_version": "ae32c/graph-utilization-assessment/v1",
            "status": "observed",
            "graph_derived_tool_usage": {
                "graph_neighbors": {"attempt_count": 2},
            },
            "graph_query_usage": {
                "attempt_count": 2,
                "successful_call_count": 2,
                "complete_query_count": 2,
                "failed_call_count": 0,
                "mode_counts": {"impact": 1, "dependencies": 1},
            },
            "source_follow_through": {
                "graph_surfaced_unique_path_count": 4,
                "verified_complete_hash_matching_path_count": 3,
                "verified_follow_through_rate": 0.75,
            },
            "claim_linkage": {
                "claim_count": 2,
                "claims_citing_graph_tool_evidence_count": 1,
            },
            "backend": {
                "active_computation_backend": "scipy",
                "backend_library_version": "1.17.0",
            },
            "provider_resource_usage": {
                "provider_reported_tokens": 900,
                "elapsed_seconds": 8.5,
            },
        },
    }
    record = build_comparison_record(
        problem_statement="inspect a controlled incident",
        provider_name="cloudflare",
        model_name="test-model",
        source_manifest_sha256="a" * 64,
        baseline_status="completed",
        baseline_response="limited source-only response",
        baseline_error=None,
        baseline_source_path="pipeline/extractor.py",
        baseline_source_sha256="b" * 64,
        graph_report=graph_report,
    )
    summary = record["graph_assisted"]["summary"]["graph_utilization_assessment"]
    assert summary["active_computation_backend"] == "scipy"
    assert summary["graph_impact_query_count"] == 1
    assert summary["graph_dependency_query_count"] == 1
    assert summary["graph_verified_follow_through_path_count"] == 3
    assert record["comparison_metrics"]["graph_assisted_graph_query_count"] == 2
    assert record["evaluation_policy"]["diagnostic_accuracy"] == "not_automatically_assessed"
    markdown = render_comparison_markdown(record)
    assert "Graph-utilization telemetry" in markdown
    assert "Active graph backend: `scipy`" in markdown


def test_graph_derived_discovery_tool_follow_through_is_measured_without_neighbors_query():
    digest = "f" * 64
    ledger = [
        _entry("E0001", "find_related_tests", {"target": "src/a.py"}, {
            "coverage_status": "complete_for_query",
            "truncated": False,
            "tests": [
                {"path": "tests/test_a.py", "source_sha256": digest, "relationship": "static_import"},
                {"path": "tests/test_text_only.py", "source_sha256": digest, "relationship": "text_reference"},
            ],
        }),
        _entry("E0002", "read_source_file", {"path": "tests/test_a.py"}, _complete_read("tests/test_a.py", digest)),
    ]
    result = build_graph_utilization_assessment(
        ledger_entries=ledger,
        graph_tools_enabled=True,
        graph_derived_tools_enabled=True,
        claim_evidence_assessment={"items": [{"evidence_refs": ["E0001"]}]},
    )
    assert result["graph_query_usage"]["attempt_count"] == 0
    assert result["graph_derived_tool_usage"]["find_related_tests"]["successful_call_count"] == 1
    assert result["source_follow_through"]["verified_paths"] == ["tests/test_a.py"]
    assert result["source_follow_through"]["graph_surfaced_unique_path_count"] == 1
    assert result["claim_linkage"]["claims_citing_graph_tool_evidence_count"] == 1


def test_partial_read_before_graph_surfacing_does_not_block_verified_follow_through():
    digest = "9" * 64
    partial = _complete_read("src/b.py", digest)
    partial.update({
        "source_range_complete": False,
        "requested_end_line": 4,
        "end_line": 2,
        "truncated": True,
    })
    ledger = [
        _entry("E0001", "read_source_file", {"path": "src/b.py"}, partial),
        _entry("E0002", "graph_neighbors", {"node": "file:src/a.py"}, {
            "coverage_status": "complete_for_query",
            "truncated": False,
            "source_paths": ["src/b.py"],
            "source_nodes": [{"path": "src/b.py", "source_sha256": digest}],
        }),
        _entry("E0003", "read_source_file", {"path": "src/b.py"}, _complete_read("src/b.py", digest)),
    ]
    result = build_graph_utilization_assessment(
        ledger_entries=ledger,
        graph_tools_enabled=True,
        graph_derived_tools_enabled=True,
    )
    follow = result["source_follow_through"]
    assert follow["paths_already_read_before_graph_surfacing"] == ["src/b.py"]
    assert follow["paths_already_verified_before_graph_surfacing"] == []
    assert follow["verified_paths"] == ["src/b.py"]
    assert follow["verified_follow_through_rate"] == 1.0
