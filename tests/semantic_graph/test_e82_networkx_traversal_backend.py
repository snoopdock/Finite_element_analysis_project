from __future__ import annotations

import copy

import pytest

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph.analysis import (
    GraphAnalysisEngine,
    GraphTraversalEngine,
    TraversalDirection,
)
from audit_engine.semantic_audit.graph.backend.networkx_traversal import (
    BackendParityError,
    BackendProjectionError,
    NetworkXGraphTraversalEngine,
)
from audit_engine.semantic_audit.graph.backend.capability_registry import create_default_registry
from audit_engine.semantic_audit.graph.service import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType


@pytest.fixture
def multigraph():
    graph = SemanticGraph()
    for name in ("A", "B", "C", "D", "E"):
        graph.add_node(SemanticNode(name, "Module", {"name": name}, {"fixture": "e8.2"}))
    for edge in (
        SemanticEdge("A", "B", "CALLS", {"ordinal": 1}, {"line": 10}),
        SemanticEdge("A", "B", "IMPORTS", {"ordinal": 2}, {"line": 11}),
        SemanticEdge("A", "B", "CALLS", {"ordinal": 3}, {"line": 12}),
        SemanticEdge("B", "C", "CALLS", {"ordinal": 4}, {"line": 20}),
        SemanticEdge("C", "A", "CALLS", {"ordinal": 5}, {"line": 30}),
        SemanticEdge("B", "B", "SELF", {"ordinal": 6}, {"line": 21}),
        SemanticEdge("D", "E", "IMPORTS", {"ordinal": 7}, {"line": 40}),
    ):
        graph.add_edge(edge)
    return graph


@pytest.mark.parametrize("direction", list(TraversalDirection))
@pytest.mark.parametrize("max_depth", [0, 1, 2, None])
@pytest.mark.parametrize("relation_types", [None, ("CALLS",), ("CALLS", "IMPORTS")])
def test_networkx_traversal_matches_reference_for_query_semantics(
    multigraph, direction, max_depth, relation_types
):
    engine = NetworkXGraphTraversalEngine(multigraph, verify_parity=True)
    result = engine.walk(
        "A",
        direction=direction,
        relation_types=relation_types,
        max_depth=max_depth,
        max_visited_nodes=4,
        max_steps=20,
    )
    reference = GraphTraversalEngine(multigraph).walk(
        "A",
        direction=direction,
        relation_types=relation_types,
        max_depth=max_depth,
        max_visited_nodes=4,
        max_steps=20,
    )
    assert result == reference
    assert engine.runtime_report()["backend_execution"]["parity_verified_queries"] == 1


def test_networkx_pipeline_preserves_parallel_edges_and_semantic_occurrence(multigraph):
    before = copy.deepcopy(multigraph.to_dict())
    engine = NetworkXGraphTraversalEngine(multigraph)
    native = engine.native_graph
    assert native.is_directed()
    assert native.is_multigraph()
    assert native.number_of_nodes() == len(multigraph.nodes)
    assert native.number_of_edges() == len(multigraph.edges)
    assert native.number_of_edges("A", "B") == 3
    assert multigraph.to_dict() == before
    report = engine.runtime_report()
    assert report["active_computation_backend"] == "networkx"
    assert report["backend_projection_type"] == "MultiDiGraph"
    assert report["backend_pipeline"]["backend"] == "networkx"
    assert report["backend_pipeline"]["lossless"] is True


def test_networkx_backend_fails_closed_when_canonical_graph_changes(multigraph):
    engine = NetworkXGraphTraversalEngine(multigraph)
    multigraph.nodes[0].attributes["changed"] = True
    with pytest.raises(BackendProjectionError, match="changed_after_networkx_projection"):
        engine.walk("A", max_depth=1)


def test_networkx_backend_rejects_corrupt_canonical_graph_before_projection(multigraph):
    multigraph.edges[0].target_id = "MISSING"
    with pytest.raises(ValueError, match="Dangling"):
        NetworkXGraphTraversalEngine(multigraph)


def test_semantic_graph_service_records_networkx_backend_and_parity(multigraph):
    service = SemanticGraphAnalysisService(
        multigraph, traversal_backend="networkx", verify_backend_parity=True
    )
    result = service.analyze(
        GraphQuery(
            "e82-dependency",
            QueryType.DEPENDENCY,
            ["A"],
            {"direction": "outgoing", "relation_types": ["CALLS"], "max_depth": 2},
        )
    )
    assert result.metadata["computation_backend"] == "networkx"
    assert result.metadata["backend_library"] == "networkx"
    assert result.metadata["backend_projection_type"] == "MultiDiGraph"
    assert result.metadata["backend_parity_status"] == "verified_against_reference_per_query"
    assert result.metadata["backend_projection_fingerprint"] == result.graph_fingerprint


def test_reference_backend_remains_available_as_explicit_oracle(multigraph):
    service = SemanticGraphAnalysisService(multigraph, traversal_backend="reference")
    result = service.analyze(
        GraphQuery("e82-reference", QueryType.DEPENDENCY, ["A"], {"max_depth": 1})
    )
    assert result.metadata["computation_backend"] == "python_reference_traversal"
    assert result.metadata["backend_parity_status"] == "reference_implementation"


def test_networkx_registry_availability_is_runtime_accurate():
    capabilities = create_default_registry().describe()
    assert capabilities["networkx"]["available"] is True
    assert capabilities["scipy"]["available"] is True
