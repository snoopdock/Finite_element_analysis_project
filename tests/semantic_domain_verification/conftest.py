import pytest

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.verification import (
    GraphAttributeConstraintVerifier,
    ObservationContractVerifier,
    ProvenanceCompletenessVerifier,
    RequiredRelationshipVerifier,
    VerifierRegistry,
    VerificationService,
)


@pytest.fixture
def domain_graph():
    graph = SemanticGraph()
    graph.add_node(SemanticNode("prod", "Module", {"lifecycle": "production"}))
    graph.add_node(SemanticNode("exp", "Module", {"lifecycle": "experimental"}))
    graph.add_node(SemanticNode("stable", "Module", {"lifecycle": "stable"}))
    graph.add_node(SemanticNode("claim:1", "ScientificClaim"))
    graph.add_node(SemanticNode("source:1", "EvidenceArtifact"))
    graph.add_edge(SemanticEdge("prod", "exp", "DEPENDS_ON", metadata={"source_id": "code:1"}))
    graph.add_edge(SemanticEdge("prod", "stable", "DEPENDS_ON", metadata={"source_id": "code:2"}))
    graph.add_edge(SemanticEdge("claim:1", "source:1", "SUPPORTED_BY", metadata={"source_id": "paper:1"}))
    return graph


@pytest.fixture
def verification_service():
    registry = VerifierRegistry()
    for verifier in (
        GraphAttributeConstraintVerifier(),
        ProvenanceCompletenessVerifier(),
        RequiredRelationshipVerifier(),
        ObservationContractVerifier(),
    ):
        registry.register(verifier)
    return VerificationService(registry)


@pytest.fixture
def dependency_result(domain_graph):
    return SemanticGraphAnalysisService(domain_graph).analyze(
        GraphQuery("domain-deps", QueryType.DEPENDENCY, ["prod"], {"max_depth": 1})
    )


@pytest.fixture
def claim_result(domain_graph):
    return SemanticGraphAnalysisService(domain_graph).analyze(
        GraphQuery(
            "claim-structure",
            QueryType.STRUCTURAL,
            ["claim:1"],
            {"direction": "outgoing", "relation_types": ["SUPPORTED_BY"]},
        )
    )
