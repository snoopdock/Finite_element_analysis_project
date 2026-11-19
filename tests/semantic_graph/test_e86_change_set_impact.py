from __future__ import annotations

from pathlib import Path

import pytest

from audit_engine.semantic_audit.core.semantic_graph import (
    SemanticEdge,
    SemanticGraph,
    SemanticNode,
)
from audit_engine.semantic_audit.graph.analysis import (
    AnalysisStatus,
    GraphAnalysisEngine,
)
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.graph.queries.validation import GraphQueryValidationError
from audit_engine.semantic_audit.graph.service import SemanticGraphAnalysisService
from audit_engine.semantic_audit.ae32b import RepositoryEvidenceTools


def change_set_graph() -> SemanticGraph:
    graph = SemanticGraph()
    nodes = [
        ("file:src/app.py", "PythonSourceFile", {"path": "src/app.py"}),
        ("module:app", "PythonModule", {"path": "src/app.py"}),
        ("symbol:app.run", "PythonSymbol", {"path": "src/app.py", "name": "run"}),
        ("file:src/lib.py", "PythonSourceFile", {"path": "src/lib.py"}),
        ("module:lib", "PythonModule", {"path": "src/lib.py"}),
        ("module:consumer", "PythonModule", {"path": "src/consumer.py"}),
        ("module:consumer2", "PythonModule", {"path": "src/consumer2.py"}),
        ("symbol:caller", "PythonSymbol", {"path": "src/consumer.py", "name": "caller"}),
        ("file:tests/test_app.py", "TestFile", {"path": "tests/test_app.py"}),
        ("file:.github/workflows/ci.yml", "WorkflowFile", {"path": ".github/workflows/ci.yml"}),
    ]
    for node_id, kind, attrs in nodes:
        graph.add_node(SemanticNode(node_id, kind, attrs, {"source_sha256": f"sha-{node_id}"}))
    edges = [
        ("file:src/app.py", "module:app", "IMPLEMENTS"),
        ("module:app", "file:src/app.py", "IMPLEMENTED_BY"),
        ("file:src/app.py", "symbol:app.run", "DEFINES"),
        ("symbol:app.run", "module:app", "MEMBER_OF"),
        ("file:src/lib.py", "module:lib", "IMPLEMENTS"),
        ("module:lib", "file:src/lib.py", "IMPLEMENTED_BY"),
        ("module:app", "module:lib", "IMPORTS"),
        ("module:lib", "module:app", "DEPENDS_ON"),
        ("module:consumer", "module:app", "IMPORTS"),
        ("module:consumer2", "module:consumer", "IMPORTS"),
        ("symbol:caller", "symbol:app.run", "CALLS"),
        ("file:tests/test_app.py", "module:app", "TESTS"),
        ("file:.github/workflows/ci.yml", "module:app", "INVOKES"),
    ]
    for index, (source, target, relation) in enumerate(edges):
        graph.add_edge(SemanticEdge(
            source, target, relation,
            {"ordinal": index + 1},
            {"path": f"evidence/{index + 1}.py", "line": index + 1},
        ))
    return graph


def query(sources=("file:src/app.py", "file:src/lib.py"), **constraints):
    return GraphQuery(
        "e86-change-set",
        QueryType.IMPACT,
        sources,
        {"max_depth": 4, "max_visited_nodes": 500, "max_traversal_steps": 3000, **constraints},
    )


def test_multi_source_impact_merges_candidates_and_attributes_sources():
    graph = change_set_graph()
    result = SemanticGraphAnalysisService(graph, traversal_backend="reference").analyze(query())
    assert result.status is AnalysisStatus.COMPLETED
    assert result.source_entities == ("file:src/app.py", "file:src/lib.py")
    metadata = result.metadata
    assert metadata["changed_source_count"] == 2
    assert metadata["unique_impact_count"] == len(metadata["impact_candidates"])
    assert metadata["shared_impact_count"] >= 1
    shared = {item["node_id"]: item for item in metadata["impact_candidates"] if item["shared_change_impact"]}
    assert "module:consumer" in shared
    assert shared["module:consumer"]["affected_by"] == ["file:src/app.py", "file:src/lib.py"]
    assert set(shared["module:consumer"]["paths_by_source"]) == {"file:src/app.py", "file:src/lib.py"}


def test_multi_source_impact_is_order_independent():
    graph = change_set_graph()
    forward = SemanticGraphAnalysisService(graph, traversal_backend="reference").analyze(query())
    reverse = SemanticGraphAnalysisService(graph, traversal_backend="reference").analyze(
        query(("file:src/lib.py", "file:src/app.py"))
    )
    assert forward.analysis_id == reverse.analysis_id
    assert forward.discovered_entities == reverse.discovered_entities
    assert forward.metadata["impact_candidates"] == reverse.metadata["impact_candidates"]
    assert forward.metadata["dependency_cycles"] == reverse.metadata["dependency_cycles"]


def test_dependency_cycle_is_reported_with_edge_evidence():
    graph = change_set_graph()
    result = SemanticGraphAnalysisService(graph, traversal_backend="reference").analyze(query())
    cycles = result.metadata["dependency_cycles"]
    assert result.metadata["cycle_analysis_status"] == "complete"
    assert len(cycles) == 1
    cycle = cycles[0]
    assert cycle["node_ids"] == ["module:app", "module:lib"]
    assert cycle["relation_types"] == ["DEPENDS_ON", "IMPORTS"]
    assert cycle["edge_count"] == 2
    evidence_ids = {item.evidence_id for item in result.evidence}
    assert set(cycle["evidence_ids"]).issubset(evidence_ids)
    assert any(item["code"] == "dependency_cycle_observed" for item in result.metadata["risk_indicators"])


def test_self_loop_is_reported_as_dependency_cycle():
    graph = change_set_graph()
    graph.add_edge(SemanticEdge("module:app", "module:app", "DEPENDS_ON", {"self": True}, {}))
    result = SemanticGraphAnalysisService(graph, traversal_backend="reference").analyze(
        query(("file:src/app.py",))
    )
    cycles = result.metadata["dependency_cycles"]
    assert any(cycle["self_loop"] and "module:app" in cycle["node_ids"] for cycle in cycles)


def test_cycle_scan_budget_is_explicitly_incomplete(monkeypatch):
    graph = change_set_graph()
    from audit_engine.semantic_audit.graph.analysis.impact import ImpactAnalyzer
    monkeypatch.setattr(ImpactAnalyzer, "MAX_CYCLE_SCAN_EDGES", 1)
    result = SemanticGraphAnalysisService(graph, traversal_backend="reference").analyze(query())
    assert result.metadata["cycle_analysis_status"] == "incomplete_edge_limit"
    assert result.status is AnalysisStatus.INCOMPLETE
    assert any(item["code"] == "dependency_cycle_scan_incomplete" for item in result.metadata["risk_indicators"])


def test_impact_traversal_budget_is_shared_across_sources():
    graph = change_set_graph()
    result = SemanticGraphAnalysisService(graph, traversal_backend="reference").analyze(
        query(max_visited_nodes=2, max_traversal_steps=2)
    )
    assert result.status is AnalysisStatus.INCOMPLETE
    assert result.metadata["truncated"] is True
    assert any(item["code"] == "impact_frontier_incomplete" for item in result.metadata["risk_indicators"])


def test_duplicate_change_sources_are_rejected():
    graph = change_set_graph()
    with pytest.raises(GraphQueryValidationError, match="duplicate"):
        SemanticGraphAnalysisService(graph).analyze(
            GraphQuery("duplicate", QueryType.IMPACT, ["module:app", "module:app"])
        )


def test_more_than_25_change_sources_are_rejected():
    graph = change_set_graph()
    for index in range(20):
        graph.add_node(SemanticNode(f"extra:{index}", "PythonModule", {"path": f"extra/{index}.py"}))
    sources = [f"extra:{index}" for index in range(20)] + [
        "file:src/app.py", "file:src/lib.py", "module:app", "module:lib", "module:consumer", "module:consumer2"
    ]
    with pytest.raises(GraphQueryValidationError, match="limited to 25"):
        SemanticGraphAnalysisService(graph).analyze(GraphQuery("too-many", QueryType.IMPACT, sources))


@pytest.mark.parametrize("backend", ["networkx", "scipy"])
def test_change_set_impact_matches_reference_for_external_backends(backend):
    graph = change_set_graph()
    reference = SemanticGraphAnalysisService(graph, traversal_backend="reference").analyze(query())
    selected = SemanticGraphAnalysisService(
        graph, traversal_backend=backend, verify_backend_parity=True,
    ).analyze(query())
    assert selected.discovered_entities == reference.discovered_entities
    assert selected.observations == reference.observations
    assert selected.evidence == reference.evidence
    assert selected.metadata["impact_candidates"] == reference.metadata["impact_candidates"]
    assert selected.metadata["dependency_cycles"] == reference.metadata["dependency_cycles"]


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_graph_neighbors_tool_accepts_multi_file_change_set(tmp_path):
    _write(tmp_path, "src/pkg/__init__.py", "")
    _write(tmp_path, "src/pkg/lib.py", "def helper():\n    return 7\n")
    _write(tmp_path, "src/pkg/app.py", "from src.pkg.lib import helper\n\ndef run():\n    return helper()\n")
    _write(tmp_path, "src/pkg/consumer.py", "from src.pkg.app import run\n\ndef main():\n    return run()\n")
    _write(tmp_path, "tests/test_app.py", "from src.pkg.app import run\n\ndef test_run():\n    assert run() == 7\n")
    _write(tmp_path, ".github/workflows/ci.yml", "name: CI\n")
    tools = RepositoryEvidenceTools(tmp_path)
    response = tools.invoke("graph_neighbors", {
        "node": "src/pkg/lib.py",
        "changed_nodes": ["src/pkg/app.py"],
        "direction": "impact",
        "max_depth": 4,
    })
    assert response["status"] == "ok"
    result = response["result"]
    assert result["change_set_summary"]["changed_source_count"] == 2
    assert result["change_set_summary"]["unique_impact_count"] >= 1
    assert "impacted_tests" in result
    assert "impacted_workflows" in result
    assert result["coverage_status"] in {"complete_for_query", "partial"}


def test_graph_neighbors_rejects_changed_nodes_outside_impact_mode(tmp_path):
    _write(tmp_path, "src/app.py", "def run():\n    return 1\n")
    tools = RepositoryEvidenceTools(tmp_path)
    response = tools.invoke("graph_neighbors", {
        "node": "src/app.py",
        "changed_nodes": ["src/app.py"],
        "direction": "both",
    })
    assert response["status"] == "error"
    assert "only when direction=impact" in response["error"]["message"]


def test_graph_neighbors_schema_advertises_bounded_change_set(tmp_path):
    _write(tmp_path, "src/app.py", "def run():\n    return 1\n")
    tools = RepositoryEvidenceTools(tmp_path)
    definition = next(
        item for item in tools.list_tools()
        if item["function"]["name"] == "graph_neighbors"
    )
    schema = definition["function"]["parameters"]
    assert schema["properties"]["changed_nodes"]["maxItems"] == 24
    assert "node" in schema["required"]
