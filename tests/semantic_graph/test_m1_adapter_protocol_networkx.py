"""M1 protocol and independent NetworkX native-adjacency contract tests."""
from __future__ import annotations

import pytest

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph.analysis.models import TraversalDirection
from audit_engine.semantic_audit.graph.analysis.traversal import GraphTraversalEngine
from audit_engine.semantic_audit.graph.backend.adapter_interface import (
    NativeAdjacencyNotSupportedError, NativeEdgeOccurrence, NativeNodeRecord, SemanticGraphAdapter,
)
from audit_engine.semantic_audit.graph.backend.networkx_adapter import NetworkXAdapter
from audit_engine.semantic_audit.graph.backend.networkx_traversal import NetworkXGraphTraversalEngine


@pytest.fixture
def graph():
    value = SemanticGraph()
    for node_id in ("A", "B", "C", "isolated"):
        value.add_node(SemanticNode(node_id, "Module", {"node": node_id}, {"fixture": "M1"}))
    value.add_edge(SemanticEdge("A", "B", "CALLS", {"ordinal": 1}, {"line": 10}))
    value.add_edge(SemanticEdge("A", "B", "CALLS", {"ordinal": 2}, {"line": 11}))
    value.add_edge(SemanticEdge("B", "A", "IMPORTS", {"ordinal": 3}, {"line": 12}))
    value.add_edge(SemanticEdge("B", "B", "SELF", {"ordinal": 4}, {"line": 13}))
    value.add_edge(SemanticEdge("B", "C", "CALLS", {"ordinal": 5}, {"line": 14}))
    return value


def test_contract_records_are_typed_and_occurrences_are_unique(graph):
    adapter = NetworkXAdapter(graph)
    nodes = list(adapter.iter_native_nodes())
    edges = list(adapter.iter_native_edge_occurrences())
    assert all(isinstance(item, NativeNodeRecord) for item in nodes)
    assert all(isinstance(item, NativeEdgeOccurrence) for item in edges)
    assert [item.occurrence_id for item in edges] == list(range(5))
    assert len({item.occurrence_id for item in edges}) == 5
    assert len([item for item in edges if item.source_id == "A" and item.target_id == "B"]) == 2


@pytest.mark.parametrize(
    ("direction", "expected"),
    [
        (TraversalDirection.OUTGOING, [2, 3, 4]),
        (TraversalDirection.INCOMING, [0, 1, 3]),
        (TraversalDirection.BOTH, [0, 1, 2, 3, 4]),
    ],
)
def test_native_local_adjacency_preserves_occurrences_and_self_loop_once(graph, direction, expected):
    adapter = NetworkXAdapter(graph)
    actual = list(adapter.iter_adjacent_edge_occurrences("B", direction))
    assert [item.occurrence_id for item in actual] == expected
    assert len(actual) == len(set(item.occurrence_id for item in actual))


def test_unknown_and_isolated_node_semantics(graph):
    adapter = NetworkXAdapter(graph)
    assert list(adapter.iter_adjacent_edge_occurrences("isolated", TraversalDirection.BOTH)) == []
    with pytest.raises(KeyError):
        list(adapter.iter_adjacent_edge_occurrences("missing", TraversalDirection.OUTGOING))


def test_native_records_do_not_leak_mutable_projection_payloads(graph):
    adapter = NetworkXAdapter(graph)
    record = next(adapter.iter_native_edge_occurrences())
    record.attributes["ordinal"] = 999
    assert next(adapter.iter_native_edge_occurrences()).attributes["ordinal"] == 1
    assert graph.edges[0].attributes["ordinal"] == 1


def test_reference_both_direction_counts_self_loop_once(graph):
    result = GraphTraversalEngine(graph).walk("B", direction=TraversalDirection.BOTH, max_depth=1)
    loops = [s for s in result.steps if s.source_id == "B" and s.target_id == "B"]
    assert len(loops) == 1
    assert result.examined_edges == 5


def test_networkx_both_direction_counts_self_loop_once(graph):
    engine = NetworkXGraphTraversalEngine(graph, verify_parity=True)
    result = engine.walk("B", direction=TraversalDirection.BOTH, max_depth=1)
    loops = [s for s in result.steps if s.source_id == "B" and s.target_id == "B"]
    assert len(loops) == 1
    assert result.examined_edges == 5


def test_runtime_report_does_not_enumerate_native_projection(graph, monkeypatch):
    engine = NetworkXGraphTraversalEngine(graph)
    def forbidden(*args, **kwargs):
        raise AssertionError("runtime_report must not enumerate native edges")
    monkeypatch.setattr(engine.native_graph, "edges", forbidden)
    monkeypatch.setattr(engine.native_graph, "number_of_nodes", forbidden)
    monkeypatch.setattr(engine.native_graph, "number_of_edges", forbidden)
    report = engine.runtime_report()
    assert report["projection_edge_occurrence_count"] == 5


def test_legacy_adapter_fails_explicitly_instead_of_scanning_projection():
    class LegacyAdapter(SemanticGraphAdapter):
        def export(self):
            return object()
        def capabilities(self):
            return {}
        def identity_mapping(self):
            return {}
        def loss_report(self):
            return {}
    with pytest.raises(NativeAdjacencyNotSupportedError):
        list(LegacyAdapter().iter_adjacent_edge_occurrences("n", TraversalDirection.OUTGOING))


def test_native_query_and_runtime_report_do_not_call_full_edge_enumerator(graph, monkeypatch):
    engine = NetworkXGraphTraversalEngine(graph, verify_parity=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("full native edge enumeration is forbidden after projection validation")

    monkeypatch.setattr(engine.native_graph, "edges", forbidden)
    result = engine.walk("B", direction=TraversalDirection.BOTH, max_depth=1)
    report = engine.runtime_report()
    assert result.examined_edges == 5
    metrics = report["backend_execution"]
    assert metrics["native_adjacency_lookups"] == 1
    assert metrics["native_edge_occurrences_read"] == 5
    assert metrics["native_edge_occurrences_returned"] == 5
    assert metrics["native_edge_occurrences_validated"] == 5


def test_native_query_does_not_rebuild_python_reference_adjacency(graph, monkeypatch):
    engine = NetworkXGraphTraversalEngine(graph, verify_parity=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("reference Python adjacency scan must not run in native-only mode")

    monkeypatch.setattr(GraphTraversalEngine, "_build_adjacency", forbidden)
    result = engine.walk("B", direction=TraversalDirection.BOTH, max_depth=1)
    assert result.examined_edges == 5


def test_networkx_traversal_calls_the_typed_adapter_adjacency_operation(graph, monkeypatch):
    engine = NetworkXGraphTraversalEngine(graph, verify_parity=False)
    original = engine.adapter.iter_adjacent_edge_occurrences
    calls = []

    def observed(node_id, direction):
        calls.append((node_id, direction))
        return original(node_id, direction)

    monkeypatch.setattr(engine.adapter, "iter_adjacent_edge_occurrences", observed)
    engine.walk("B", direction=TraversalDirection.BOTH, max_depth=1)
    assert calls == [("B", TraversalDirection.BOTH)]


def test_projection_is_directed_multigraph_and_keeps_isolated_nodes(graph):
    adapter = NetworkXAdapter(graph)
    native = adapter.export()
    assert native.is_directed()
    assert native.is_multigraph()
    assert native.number_of_nodes() == 4
    assert native.number_of_edges() == 5
    assert "isolated" in native


def test_native_edge_mapping_corruption_fails_closed(graph):
    adapter = NetworkXAdapter(graph)
    source, target, key = adapter.identity_mapping()["semantic_edge_occurrence_to_backend"][0]
    adapter.export()[source][target][key]["__ae32_semantic_edge_occurrence__"] = 99
    with pytest.raises(ValueError, match="occurrence_mapping_invalid"):
        list(adapter.iter_adjacent_edge_occurrences("B", TraversalDirection.BOTH))


def test_native_payload_mutation_is_detected_by_traversal_engine(graph):
    engine = NetworkXGraphTraversalEngine(graph, verify_parity=False)
    engine.native_graph["A"]["B"][0]["relation"] = "CORRUPTED"
    with pytest.raises(RuntimeError, match="semantic_payload_mismatch"):
        engine.walk("B", direction=TraversalDirection.BOTH, max_depth=1)


def test_capability_declaration_never_implies_acceptance(graph):
    adapter = NetworkXAdapter(graph)
    capabilities = adapter.capabilities()
    assert capabilities["acceptance_status"] == "not_established_by_capability_declaration"
    assert capabilities["native_adjacency_directions"] == ["outgoing", "incoming", "both"]

def test_registry_separates_discovery_from_conformance_and_approval():
    from audit_engine.semantic_audit.graph.backend.capability_registry import create_default_registry

    capabilities = create_default_registry().describe()
    networkx_state = capabilities["networkx"]["acceptance_state"]
    assert networkx_state["implementation"] == "present"
    assert networkx_state["native_adjacency_implementation"] == "implemented_unvalidated"
    assert networkx_state["native_adjacency_conformance"] == "not_run"
    assert networkx_state["production_approval"] is False
    scipy_state = capabilities["scipy"]["acceptance_state"]
    assert scipy_state["native_adjacency_implementation"] == "implemented_unvalidated"
    assert scipy_state["native_adjacency_conformance"] == "not_run"
    assert scipy_state["production_approval"] is False
    igraph_state = capabilities["igraph"]["acceptance_state"]
    assert igraph_state["native_adjacency_implementation"] == "implemented_unvalidated"
    assert igraph_state["native_adjacency_conformance"] == "not_run"
    assert igraph_state["production_approval"] is False
    graph_tool_state = capabilities["graph-tool"]["acceptance_state"]
    assert graph_tool_state["native_adjacency_implementation"] == "implemented_unvalidated"
    assert graph_tool_state["native_adjacency_conformance"] == "not_run"
    assert graph_tool_state["production_approval"] is False
    snap_state = capabilities["snap"]["acceptance_state"]
    assert snap_state["native_adjacency_implementation"] == "not_implemented"
    assert snap_state["production_approval"] is False