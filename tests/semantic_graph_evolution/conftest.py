from __future__ import annotations

import pytest

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph.analysis.context import SemanticContext


@pytest.fixture
def base_graph():
    graph = SemanticGraph()
    graph.add_node(SemanticNode('a', 'Module', {'lifecycle': 'production'}))
    graph.add_node(SemanticNode('b', 'Module', {'lifecycle': 'stable'}))
    graph.add_node(SemanticNode('c', 'Module'))
    graph.add_edge(SemanticEdge('a', 'b', 'DEPENDS_ON', metadata={'source_id': 'code:1'}))
    return graph


@pytest.fixture
def base_context():
    return SemanticContext(
        graph_schema_version='semantic_graph/v1',
        relationship_vocabulary_version='repo-relations/v1',
        projection_contract_version='code-projection/v1',
        analysis_contract_version='semantic_graph_analysis_contract/v2',
    )
