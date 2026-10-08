import pytest

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.analysis import VerificationStatus
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.verification import (
    GraphAttributeConstraintVerifier,
    ProvenanceCompletenessVerifier,
    RequiredRelationshipVerifier,
    VerificationContext,
    VerificationDecision,
    VerificationObligation,
)


def test_graph_attribute_verifier_confirms_production_to_experimental(dependency_result, domain_graph):
    obs = next(item for item in dependency_result.observations if item.object_id == "exp")
    obligation = VerificationObligation.from_analysis_result(
        dependency_result,
        obligation_type="graph_attribute_constraint",
        observation_ids=[obs.observation_id],
        evidence_ids=list(obs.evidence_ids),
        parameters={
            "relation_types": ["DEPENDS_ON"],
            "source_attributes": {"lifecycle": "production"},
            "target_attributes": {"lifecycle": "experimental"},
        },
    )
    attempt = GraphAttributeConstraintVerifier().verify(
        obligation, VerificationContext(dependency_result, domain_graph)
    )
    assert attempt.decision is VerificationDecision.CONFIRMED
    assert attempt.evidence_state is VerificationStatus.VALIDATED


def test_graph_attribute_verifier_refutes_stable_target(dependency_result, domain_graph):
    obs = next(item for item in dependency_result.observations if item.object_id == "stable")
    obligation = VerificationObligation.from_analysis_result(
        dependency_result,
        obligation_type="graph_attribute_constraint",
        observation_ids=[obs.observation_id],
        evidence_ids=list(obs.evidence_ids),
        parameters={"target_attributes": {"lifecycle": "experimental"}},
    )
    attempt = GraphAttributeConstraintVerifier().verify(
        obligation, VerificationContext(dependency_result, domain_graph)
    )
    assert attempt.decision is VerificationDecision.REFUTED


def test_graph_verifier_requires_graph_context(dependency_result):
    obligation = VerificationObligation.from_analysis_result(
        dependency_result,
        obligation_type="graph_attribute_constraint",
        parameters={"source_attributes": {"lifecycle": "production"}},
    )
    with pytest.raises(ValueError, match="requires the canonical SemanticGraph"):
        GraphAttributeConstraintVerifier().verify(obligation, VerificationContext(dependency_result))


def test_graph_context_rejects_fingerprint_mismatch(dependency_result, domain_graph):
    different = SemanticGraph()
    different.add_node(SemanticNode("prod", "Module"))
    obligation = VerificationObligation.from_analysis_result(
        dependency_result, obligation_type="graph_attribute_constraint"
    )
    with pytest.raises(ValueError, match="graph fingerprint"):
        VerificationContext(dependency_result, different).validate_obligation_binding(obligation)


def test_required_relationship_confirms_claim_support(claim_result, domain_graph):
    obligation = VerificationObligation.from_analysis_result(
        claim_result,
        obligation_type="required_relationship",
        parameters={"relation_types": ["SUPPORTED_BY"], "target_entity_types": ["EvidenceArtifact"]},
    )
    attempt = RequiredRelationshipVerifier().verify(
        obligation, VerificationContext(claim_result, domain_graph)
    )
    assert attempt.decision is VerificationDecision.CONFIRMED
    assert attempt.details["match_counts"]["claim:1"] == 1


def test_required_relationship_refutes_missing_support():
    graph = SemanticGraph()
    graph.add_node(SemanticNode("claim:missing", "ScientificClaim"))
    result = SemanticGraphAnalysisService(graph).analyze(
        GraphQuery("missing", QueryType.STRUCTURAL, ["claim:missing"], {"direction": "outgoing"})
    )
    obligation = VerificationObligation.from_analysis_result(
        result,
        obligation_type="required_relationship",
        parameters={"relation_types": ["SUPPORTED_BY"]},
    )
    attempt = RequiredRelationshipVerifier().verify(obligation, VerificationContext(result, graph))
    assert attempt.decision is VerificationDecision.REFUTED
    assert attempt.details["missing_entity_ids"] == ["claim:missing"]


def test_provenance_completeness_confirms_source_identity(dependency_result):
    obs = dependency_result.observations[0]
    obligation = VerificationObligation.from_analysis_result(
        dependency_result,
        obligation_type="provenance_completeness",
        observation_ids=[obs.observation_id],
        evidence_ids=list(obs.evidence_ids),
        parameters={"required_paths": ["edge_metadata.source_id"]},
    )
    attempt = ProvenanceCompletenessVerifier().verify(
        obligation, VerificationContext(dependency_result)
    )
    assert attempt.decision is VerificationDecision.CONFIRMED


def test_provenance_completeness_refutes_missing_path(domain_graph):
    domain_graph.edges[0].metadata.clear()
    result = SemanticGraphAnalysisService(domain_graph).analyze(
        GraphQuery("prov-missing", QueryType.DEPENDENCY, ["prod"], {"max_depth": 1})
    )
    obs = next(item for item in result.observations if item.object_id == "exp")
    obligation = VerificationObligation.from_analysis_result(
        result,
        obligation_type="provenance_completeness",
        observation_ids=[obs.observation_id],
        evidence_ids=list(obs.evidence_ids),
        parameters={"required_paths": ["edge_metadata.source_id"]},
    )
    attempt = ProvenanceCompletenessVerifier().verify(obligation, VerificationContext(result))
    assert attempt.decision is VerificationDecision.REFUTED
    assert attempt.details["missing_by_evidence"]
