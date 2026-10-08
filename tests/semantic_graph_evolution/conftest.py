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

@pytest.fixture
def copy_graph():
    def _copy(graph):
        new = SemanticGraph()
        for node in graph.nodes:
            new.add_node(SemanticNode(node.node_id, node.entity_type, dict(node.attributes), dict(node.metadata)))
        for edge in graph.edges:
            new.add_edge(SemanticEdge(edge.source_id, edge.target_id, edge.relation_type, dict(edge.attributes), dict(edge.metadata)))
        return new
    return _copy


@pytest.fixture
def analysis_receipt_factory():
    from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
    from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
    from audit_engine.semantic_audit.verification import (
        ObservationContractVerifier,
        VerificationObligation,
        VerificationService,
        VerifierRegistry,
    )

    def _make(graph, context, *, query_id='g321', source='a', query_type=QueryType.DEPENDENCY, constraints=None):
        constraints = dict(constraints or {'max_depth': 1})
        result = SemanticGraphAnalysisService(graph, semantic_context=context).analyze(
            GraphQuery(query_id, query_type, [source], constraints)
        )
        if not result.observations:
            return result, None
        observation = result.observations[0]
        obligation = VerificationObligation.from_analysis_result(
            result,
            obligation_type='observation_contract',
            observation_ids=[observation.observation_id],
            evidence_ids=list(observation.evidence_ids),
            requested_verifier_ids=['observation-contract'],
            parameters={
                'subject_id': observation.subject_id,
                'predicate': observation.predicate,
                'object_id': observation.object_id,
            },
        )
        registry = VerifierRegistry()
        registry.register(ObservationContractVerifier())
        receipt = VerificationService(registry).verify(
            obligation,
            result,
            verifier_id='observation-contract',
        )
        return result, receipt

    return _make
