"""GB-01.1: stable graph core behavior on the Python 3.9 SNAP runtime.

The live CPython 3.9 smoke job performs the interpreter-specific import.
These tests protect semantic invariants on the repository's standard interpreter.
"""
from typing import Optional, get_type_hints

import pytest

from audit_engine.semantic_audit.core.semantic_graph import (
    SemanticGraph, SemanticNode, SemanticEdge,
)
from audit_engine.semantic_audit.graph.backend.backend_factory import BackendFactory
from audit_engine.semantic_audit.graph.backend.execution_context import BackendExecutionContext
from audit_engine.semantic_audit.graph.backend.optional_backend_support import make_projection


def test_get_node_has_backward_compatible_optional_annotation():
    hints = get_type_hints(SemanticGraph.get_node)
    assert hints["return"] == Optional[SemanticNode]
    assert hints["node_id"] is str


def test_missing_node_remains_none_and_non_mutating():
    graph = SemanticGraph()
    graph.add_node(SemanticNode("A", "Concept"))
    before = graph.to_dict()
    assert graph.get_node("missing") is None
    assert graph.get_node("A").node_id == "A"
    assert graph.to_dict() == before


def test_semantic_graph_invariants_unchanged():
    graph = SemanticGraph()
    graph.add_node(SemanticNode("A", "Concept"))
    graph.add_node(SemanticNode("B", "Concept"))
    with pytest.raises(ValueError, match="Duplicate"):
        graph.add_node(SemanticNode("A", "Concept"))
    with pytest.raises(ValueError, match="not present"):
        graph.add_edge(SemanticEdge("A", "unknown", "RELATED_TO"))
    graph.add_edge(SemanticEdge("A", "B", "REL", {"count": 1}))
    graph.add_edge(SemanticEdge("A", "B", "REL", {"count": 2}))
    graph.add_edge(SemanticEdge("B", "B", "SELF"))
    assert len(graph.edges) == 3
    assert graph.to_dict()["edges"][0]["attributes"]["count"] == 1
    assert graph.to_dict()["edges"][1]["attributes"]["count"] == 2


def test_optional_projection_preserves_repeated_edges_and_core_unchanged():
    graph = SemanticGraph()
    graph.add_node(SemanticNode("α", "Concept", {"labels": ["one"]}, {"source": "doc"}))
    graph.add_node(SemanticNode("β", "Proposition"))
    graph.add_edge(SemanticEdge("α", "β", "SUPPORTS"))
    graph.add_edge(SemanticEdge("α", "β", "REFERS_TO"))
    graph.add_edge(SemanticEdge("β", "β", "SELF"))
    before = graph.to_dict()
    projection = make_projection(graph)
    assert projection.node_to_index == {"α": 0, "β": 1}
    assert [e["occurrence"] for e in projection.edges] == [0, 1, 2]
    assert [(e["source_index"], e["target_index"]) for e in projection.edges] == [(0,1),(0,1),(1,1)]
    projection.nodes[0]["attributes"]["labels"].append("mutated")
    assert graph.to_dict() == before


def test_snap_factory_remains_lazy_without_optional_library():
    assert BackendFactory._ADAPTERS["snap"] == ("snap_adapter", "SNAPAdapter")
    context = BackendExecutionContext(SemanticGraph())
    assert context.graph is not None


def test_native_snap_adapter_if_available():
    pytest.importorskip("snap", reason="Stanford SNAP is binary-only; verified on Python 3.9 CI")
    from tools.gb01_native_smoke import run
    result = run("snap")
    assert result["status"] == "passed"
    assert result["nodes"] == 2
    assert result["edge_occurrences"] == 3
    assert result["metadata_verified"] is True
