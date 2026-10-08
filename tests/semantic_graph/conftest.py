import pytest

from audit_engine.semantic_audit.core.semantic_graph import (
    SemanticEdge,
    SemanticGraph,
    SemanticNode,
)


@pytest.fixture
def software_graph() -> SemanticGraph:
    graph = SemanticGraph()
    for node_id, entity_type in (
        ("app.py", "SoftwareModule"),
        ("service.py", "SoftwareModule"),
        ("db.py", "SoftwareModule"),
        ("logging.info", "Symbol"),
        ("isolated.py", "SoftwareModule"),
    ):
        graph.add_node(SemanticNode(node_id=node_id, entity_type=entity_type))

    graph.add_edge(
        SemanticEdge(
            source_id="app.py",
            target_id="service.py",
            relation_type="IMPORTS",
            metadata={"line": 1, "extractor": "ast"},
        )
    )
    graph.add_edge(
        SemanticEdge(
            source_id="service.py",
            target_id="db.py",
            relation_type="IMPORTS",
            metadata={"line": 2, "extractor": "ast"},
        )
    )
    graph.add_edge(
        SemanticEdge(
            source_id="app.py",
            target_id="logging.info",
            relation_type="USES",
            metadata={"line": 8, "extractor": "ast"},
        )
    )
    return graph


@pytest.fixture
def cyclic_graph() -> SemanticGraph:
    graph = SemanticGraph()
    for node_id in ("A", "B", "C"):
        graph.add_node(SemanticNode(node_id=node_id, entity_type="Node"))
    graph.add_edge(SemanticEdge("A", "B", "DEPENDS_ON"))
    graph.add_edge(SemanticEdge("B", "C", "DEPENDS_ON"))
    graph.add_edge(SemanticEdge("C", "A", "DEPENDS_ON"))
    return graph
