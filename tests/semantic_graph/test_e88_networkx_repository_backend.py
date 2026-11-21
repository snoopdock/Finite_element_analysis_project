from __future__ import annotations

from pathlib import Path

import pytest

from audit_engine.semantic_audit.ae32b.evidence_tools import RepositoryEvidenceTools
from audit_engine.semantic_audit.graph.analysis import GraphTraversalEngine, TraversalDirection
from audit_engine.semantic_audit.graph.backend.networkx_traversal import NetworkXGraphTraversalEngine
from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode

FIXTURE = Path(__file__).resolve().parents[1] / "semantic_audit" / "fixtures" / "ae32c_provider_interface_incident"


def _graph() -> SemanticGraph:
    graph = SemanticGraph()
    for node_id in ("a", "b", "c"):
        graph.add_node(SemanticNode(node_id, "Module", {"path": f"{node_id}.py"}, {}))
    graph.add_edge(SemanticEdge("a", "b", "CALLS", {}, {"path": "a.py", "line": 1}))
    graph.add_edge(SemanticEdge("b", "c", "IMPORTS", {}, {"path": "b.py", "line": 2}))
    graph.add_edge(SemanticEdge("c", "a", "CALLS", {}, {"path": "c.py", "line": 3}))
    return graph


def test_networkx_query_uses_native_successor_predecessor_adjacency(monkeypatch):
    graph = _graph()
    engine = NetworkXGraphTraversalEngine(graph, verify_parity=True)
    expected = GraphTraversalEngine(graph).walk(
        "a", direction=TraversalDirection.OUTGOING, relation_types=("CALLS",), max_depth=2
    )

    # The full native projection was checked at construction. Query execution
    # must use per-node succ/pred adjacency and must not rescan graph.edges.
    import networkx as nx

    def forbidden_edges(_self, *args, **kwargs):
        raise AssertionError("full_native_edge_scan_during_query")

    monkeypatch.setattr(nx.MultiDiGraph, "edges", property(forbidden_edges))
    result = engine.walk(
        "a", direction=TraversalDirection.OUTGOING, relation_types=("CALLS",), max_depth=2
    )
    assert result == expected
    runtime = engine.runtime_report()
    assert runtime["backend_native_query_mode"] == "networkx_successor_predecessor_adjacency"
    assert runtime["backend_execution"]["native_adjacency_lookups"] >= 1
    assert runtime["backend_execution"]["native_edge_occurrences_read"] >= 1
    assert runtime["backend_execution"]["parity_verified_queries"] == 1


def test_repository_backend_query_surfaces_and_reads_hash_bound_source_files():
    tools = RepositoryEvidenceTools(FIXTURE, graph_backend="networkx")
    query = tools.invoke("graph_neighbors", {
        "node": "symbol:pipeline.extractor::extract",
        "direction": "incoming",
        "relation_types": ["CALLS"],
        "max_depth": 1,
        "max_results": 20,
    })
    assert query["status"] == "ok"
    result = query["result"]
    assert result["coverage_status"] == "complete_for_query"
    assert {"main.py", "tests/checks.py"}.issubset(set(result["source_paths"]))

    expected_hashes = {}
    for item in result["evidence"]:
        metadata = item["provenance"]["edge_metadata"]
        expected_hashes[metadata["path"]] = metadata["source_sha256"]
    for path in ("main.py", "tests/checks.py"):
        total_lines = len(tools.contents[path].splitlines())
        read = tools.invoke("read_source_file", {
            "path": path, "start_line": 1, "end_line": total_lines,
        })
        assert read["status"] == "ok"
        assert read["result"]["source_sha256"] == expected_hashes[path]
        assert read["result"]["source_range_complete"] is True
        assert read["result"]["content_omitted"] is False

    runtime = tools.graph_runtime_report()
    assert runtime["active_computation_backend"] == "networkx"
    assert runtime["external_backend_adapters_active"] == ["networkx"]
    assert runtime["context_backend_bypass_count"] == 0
    assert runtime["backend_execution"]["parity_verified_queries"] == 1
    assert runtime["backend_execution"]["parity_failures"] == 0


def test_repository_conformance_runner_requires_native_context_tool_routing():
    from tools.gb04_repository_backend_conformance import run_repository_conformance

    report = run_repository_conformance(FIXTURE, "networkx")
    assert report["status"] == "passed"
    assert report["graph_to_repository_follow_through"]["verified_read_count"] == 2
    assert report["backend_execution"]["parity_verified_queries"] >= 3
    assert report["backend_queries"]["trace_execution_context"]["backend_execution"] == (
        "networkx_native_successor_predecessor_adjacency"
    )
    assert report["backend_queries"]["trace_execution_context"]["telemetry"]["native_adjacency_lookups"] >= 1
    assert report["backend_queries"]["trace_nested_find_workflow_context"]["telemetry"]["parity_verified"] >= 1
    assert report["backend_queries"]["find_workflow_context"]["backend_execution"] == (
        "networkx_native_successor_predecessor_adjacency"
    )
    assert report["backend_queries"]["find_workflow_context"]["telemetry"]["native_adjacency_lookups"] >= 1

    # Context-tool counters belong to RepositoryEvidenceTools, not the
    # traversal engine's backend_execution counter set. The runner must
    # publish them as a separate top-level report section.
    context_telemetry = report["context_operation_telemetry"]
    assert set(context_telemetry) == {
        "trace_execution_context",
        "trace_execution_context.workflow_context",
        "find_workflow_context",
    }
    for operation in (
        "trace_execution_context",
        "trace_execution_context.workflow_context",
        "find_workflow_context",
    ):
        observed = context_telemetry[operation]
        assert observed["adjacency_queries_attempted"] >= 1
        assert observed["adjacency_queries_succeeded"] == observed["adjacency_queries_attempted"]
        assert observed["adjacency_queries_failed"] == 0
        assert observed["native_adjacency_lookups"] >= 1
        assert observed["parity_verified"] >= 1
        assert observed["parity_failures"] == 0


def test_context_tools_use_backend_neutral_graph_queries(monkeypatch):
    def forbidden_context_hook(*args, **kwargs):
        raise AssertionError("backend_specific_context_hook_must_not_be_used")

    monkeypatch.setattr(NetworkXGraphTraversalEngine, "context_edges", forbidden_context_hook)
    tools = RepositoryEvidenceTools(FIXTURE, graph_backend="networkx")

    trace = tools.invoke("trace_execution_context", {
        "target": "pipeline/extractor.py",
        "max_depth": 4,
        "max_results": 20,
    })
    workflow = tools.invoke("find_workflow_context", {
        "target": "pipeline/extractor.py",
        "max_results": 20,
    })
    assert trace["status"] == "ok"
    assert workflow["status"] == "ok"

    runtime = tools.graph_runtime_report()
    assert runtime["context_backend_bypass_count"] == 0
    telemetry = runtime["context_operation_telemetry"]
    for operation in ("trace_execution_context", "find_workflow_context"):
        observed = telemetry[operation]
        assert observed["adjacency_queries_attempted"] >= 1
        assert observed["adjacency_queries_succeeded"] == observed["adjacency_queries_attempted"]
        assert observed["adjacency_queries_failed"] == 0
        assert observed["native_adjacency_lookups"] >= observed["adjacency_queries_attempted"]
        assert observed["parity_verified"] == observed["adjacency_queries_succeeded"]
        assert observed["parity_failures"] == 0
    nested = telemetry["trace_execution_context.workflow_context"]
    assert nested["adjacency_queries_attempted"] >= 1
    assert nested["native_adjacency_lookups"] >= nested["adjacency_queries_attempted"]


def test_repository_conformance_runner_reports_snapshot_and_source_manifest():
    from tools.gb04_repository_backend_conformance import run_repository_conformance

    report = run_repository_conformance(FIXTURE, "networkx")
    snapshot = report["repository_snapshot"]
    assert snapshot["evidence_index_status"] == "complete"
    assert snapshot["graph_node_count"] == 26
    assert snapshot["graph_edge_count"] == 41
    assert snapshot["graph_fingerprint"]
    assert snapshot["source_manifest_sha256"]
    assert report["side_effects"] == {
        "repository_code_executed": False,
        "tests_executed_by_backend": False,
        "source_files_modified": False,
        "network_calls_performed": False,
        "provider_calls_made": False,
    }


def test_native_backend_workflow_avoids_flat_layout_editable_install_and_adds_repo_runner():
    workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/e85-native-graph-backend-conformance.yml").read_text(encoding="utf-8")
    assert "pip install -e" not in workflow
    assert "python tools/gb04_repository_backend_conformance.py" in workflow
    assert "python-version: \"3.9.19\"" in workflow
    assert "SNAP AE-32C adapter acceptance: NOT YET ACCEPTED" in workflow

    pyproject = (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(encoding="utf-8")
    assert 'igraph>=0.11,<2.0' in pyproject

    snap_smoke = (Path(__file__).resolve().parents[2] / "tools/snap_python39_compatibility_smoke.py").read_text(encoding="utf-8")
    compile(snap_smoke, "snap_python39_compatibility_smoke.py", "exec")
    assert "ae32c_adapter_acceptance\": \"not_run\"" in snap_smoke
