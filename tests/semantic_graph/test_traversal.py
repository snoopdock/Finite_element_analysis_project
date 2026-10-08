import pytest

from audit_engine.semantic_audit.graph.analysis import (
    GraphTraversalEngine,
    GraphTraversalError,
    TraversalDirection,
)


def test_outgoing_traversal_preserves_semantic_ids(software_graph):
    result = GraphTraversalEngine(software_graph).walk(
        "app.py",
        relation_types=("IMPORTS",),
        max_depth=2,
    )
    assert result.visited_nodes == ("service.py", "db.py")
    assert all(not value.isdigit() for value in result.visited_nodes)


def test_traversal_respects_relation_filter(software_graph):
    result = GraphTraversalEngine(software_graph).walk(
        "app.py",
        relation_types=("USES",),
        max_depth=1,
    )
    assert result.visited_nodes == ("logging.info",)


def test_incoming_traversal(software_graph):
    result = GraphTraversalEngine(software_graph).walk(
        "db.py",
        direction=TraversalDirection.INCOMING,
        relation_types=("IMPORTS",),
        max_depth=2,
    )
    assert result.visited_nodes == ("service.py", "app.py")


def test_cycle_safe_traversal(cyclic_graph):
    result = GraphTraversalEngine(cyclic_graph).walk(
        "A",
        relation_types=("DEPENDS_ON",),
        max_depth=None,
    )
    assert result.visited_nodes == ("B", "C")


def test_zero_depth_returns_no_hits(software_graph):
    result = GraphTraversalEngine(software_graph).walk("app.py", max_depth=0)
    assert result.hits == ()


def test_negative_depth_rejected(software_graph):
    with pytest.raises(GraphTraversalError):
        GraphTraversalEngine(software_graph).walk("app.py", max_depth=-1)


def test_traversal_evidence_retains_edge_metadata(software_graph):
    result = GraphTraversalEngine(software_graph).walk(
        "app.py",
        relation_types=("IMPORTS",),
        max_depth=1,
    )
    assert len(result.evidence) == 1
    assert result.evidence[0].provenance["edge_metadata"]["line"] == 1
    assert result.evidence[0].verification_status.value == "observed"


def test_parallel_edges_are_preserved_as_distinct_observations():
    from audit_engine.semantic_audit.core.semantic_graph import (
        SemanticEdge,
        SemanticGraph,
        SemanticNode,
    )
    from audit_engine.semantic_audit.graph.analysis.helpers import observations_from_traversal

    graph = SemanticGraph()
    graph.add_node(SemanticNode("A", "Node"))
    graph.add_node(SemanticNode("B", "Node"))
    graph.add_edge(SemanticEdge("A", "B", "IMPORTS", metadata={"line": 1}))
    graph.add_edge(SemanticEdge("A", "B", "USES", metadata={"line": 2}))

    traversal = GraphTraversalEngine(graph).walk("A", max_depth=1)
    observations = observations_from_traversal(traversal)

    assert len(traversal.steps) == 2
    assert {(item.predicate, item.object_id) for item in observations} == {
        ("IMPORTS", "B"),
        ("USES", "B"),
    }
