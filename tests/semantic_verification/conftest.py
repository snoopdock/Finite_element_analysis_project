
import pytest

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType


@pytest.fixture
def verification_graph() -> SemanticGraph:
    graph = SemanticGraph()
    for node_id in ("A", "B", "C"):
        graph.add_node(SemanticNode(node_id=node_id, entity_type="Module"))
    graph.add_edge(
        SemanticEdge(
            source_id="A",
            target_id="B",
            relation_type="DEPENDS_ON",
            metadata={"source_id": "source-1", "line": 10},
        )
    )
    graph.add_edge(
        SemanticEdge(
            source_id="B",
            target_id="C",
            relation_type="DEPENDS_ON",
            metadata={"source_id": "source-2", "line": 20},
        )
    )
    return graph


@pytest.fixture
def dependency_result(verification_graph):
    return SemanticGraphAnalysisService(verification_graph).analyze(
        GraphQuery(
            "verification-dependency",
            QueryType.DEPENDENCY,
            ["A"],
            {"max_depth": 2},
        )
    )
