from copy import deepcopy

from audit_engine.semantic_audit.graph.analysis import (
    edge_fingerprint,
    graph_fingerprint,
)


def test_graph_fingerprint_is_deterministic(software_graph):
    first = graph_fingerprint(software_graph)
    second = graph_fingerprint(software_graph)
    assert first == second
    assert first.startswith("graph:")


def test_graph_fingerprint_is_insertion_order_independent(software_graph):
    reordered = deepcopy(software_graph)
    reordered.nodes = list(reversed(reordered.nodes))
    reordered.edges = list(reversed(reordered.edges))
    assert graph_fingerprint(reordered) == graph_fingerprint(software_graph)


def test_graph_fingerprint_changes_when_semantics_change(software_graph):
    before = graph_fingerprint(software_graph)
    software_graph.edges[0].relation_type = "DEPENDS_ON"
    after = graph_fingerprint(software_graph)
    assert after != before


def test_edge_fingerprint_includes_metadata(software_graph):
    edge = software_graph.edges[0]
    first = edge_fingerprint(edge)
    edge.metadata["line"] = 99
    assert edge_fingerprint(edge) != first
