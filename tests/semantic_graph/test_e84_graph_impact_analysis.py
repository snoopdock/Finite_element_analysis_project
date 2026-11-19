from __future__ import annotations

import pytest

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph.analysis import AnalysisStatus, ImpactAnalyzer
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.graph.service import SemanticGraphAnalysisService


def impact_graph():
    graph = SemanticGraph()
    nodes = [
        ("file:src/app.py", "PythonSourceFile", {"path": "src/app.py"}),
        ("module:app", "PythonModule", {"path": "src/app.py"}),
        ("symbol:app.run", "PythonSymbol", {"path": "src/app.py", "name": "run"}),
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


def _query(source="file:src/app.py", **constraints):
    return GraphQuery(
        "impact-query",
        QueryType.IMPACT,
        [source],
        {"max_depth": 3, **constraints},
    )


def test_impact_analysis_resolves_file_ownership_and_reverse_dependencies():
    graph = impact_graph()
    service = SemanticGraphAnalysisService(graph, traversal_backend="reference")
    result = service.analyze(_query())
    assert result.status is AnalysisStatus.COMPLETED
    assert set(result.discovered_entities) == {
        "module:consumer", "module:consumer2", "symbol:caller",
        "file:tests/test_app.py", "file:.github/workflows/ci.yml",
    }
    assert result.metadata["direct_impact_count"] == 4
    assert result.metadata["transitive_impact_count"] == 1
    assert result.metadata["runtime_execution_proven"] is False
    assert result.metadata["severity_assessed"] is False
    assert result.metadata["semantic_correctness_assessed"] is False
    assert any(item.predicate == "IMPLEMENTS" for item in result.observations)
    assert any(item.predicate == "IMPORTS" for item in result.observations)
    assert any(item.predicate == "TESTS" for item in result.observations)


def test_impact_analysis_can_start_from_module_or_symbol():
    graph = impact_graph()
    service = SemanticGraphAnalysisService(graph, traversal_backend="reference")
    module_result = service.analyze(_query("module:app"))
    symbol_result = service.analyze(_query("symbol:app.run"))
    assert "module:consumer" in module_result.discovered_entities
    assert "symbol:caller" in symbol_result.discovered_entities


def test_impact_analysis_is_bounded_and_fails_closed_as_incomplete():
    graph = impact_graph()
    service = SemanticGraphAnalysisService(graph, traversal_backend="reference")
    result = service.analyze(_query(max_visited_nodes=1))
    assert result.status is AnalysisStatus.INCOMPLETE
    assert result.metadata["truncated"] is True
    assert result.metadata["stop_reason"] == "max_visited_nodes"


def test_impact_analysis_rejects_multiple_sources():
    graph = impact_graph()
    service = SemanticGraphAnalysisService(graph, traversal_backend="reference")
    query = GraphQuery("multi", QueryType.IMPACT, ["module:app", "module:consumer"])
    with pytest.raises(ValueError, match="exactly one"):
        service.analyze(query)


@pytest.mark.parametrize("backend", ["networkx", "scipy"])
def test_impact_analysis_uses_selected_external_backend_with_reference_parity(backend):
    graph = impact_graph()
    query = _query()
    reference = SemanticGraphAnalysisService(graph, traversal_backend="reference").analyze(query)
    selected = SemanticGraphAnalysisService(
        graph, traversal_backend=backend, verify_backend_parity=True,
    )
    result = selected.analyze(query)
    assert result.discovered_entities == reference.discovered_entities
    assert result.observations == reference.observations
    assert result.evidence == reference.evidence
    runtime = selected.engine.traversal_engine.runtime_report()
    assert runtime["active_computation_backend"] == backend
    assert runtime["backend_execution"]["parity_verified_queries"] > 1
