from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph.analysis import VerificationStatus
from audit_engine.semantic_audit.promotion import (
    CandidatePromotionPolicy,
    CandidatePromotionService,
)
from audit_engine.semantic_audit.verification import (
    CandidateKnowledge,
    VerificationDecision,
    VerificationObligation,
)


def _verified_candidate(dependency_result, verification_service):
    obs = next(item for item in dependency_result.observations if item.subject_id == "prod" and item.object_id == "exp")
    candidate = CandidateKnowledge.create(
        subject_id="prod", predicate="DEPENDS_ON", object_id="exp", evidence_ids=obs.evidence_ids
    )
    obligation = VerificationObligation.from_analysis_result(
        dependency_result,
        obligation_type="observation_contract",
        observation_ids=[obs.observation_id],
        evidence_ids=list(obs.evidence_ids),
        requested_verifier_ids=["observation-contract"],
        parameters={
            "candidate_id": candidate.candidate_id,
            "subject_id": candidate.subject_id,
            "predicate": candidate.predicate,
            "object_id": candidate.object_id,
        },
    )
    receipt = verification_service.verify(
        obligation, dependency_result, verifier_id="observation-contract"
    )
    assert receipt.decision is VerificationDecision.CONFIRMED
    return candidate, obligation, receipt


def target_graph():
    graph = SemanticGraph()
    graph.add_node(SemanticNode("prod", "Module"))
    graph.add_node(SemanticNode("exp", "Module"))
    return graph


def test_verified_candidate_can_be_promoted(dependency_result, verification_service):
    candidate, obligation, receipt = _verified_candidate(dependency_result, verification_service)
    graph = target_graph()
    result = CandidatePromotionService().promote(
        candidate=candidate,
        obligation=obligation,
        receipt=receipt,
        target_graph=graph,
        policy=CandidatePromotionPolicy(
            "promotion.default", "1", allowed_verifier_ids=("observation-contract",)
        ),
    )
    assert result.promoted
    assert len(graph.edges) == 1
    assert graph.edges[0].metadata["promotion"]["receipt_id"] == receipt.receipt_id


def test_promotion_can_map_candidate_predicate(dependency_result, verification_service):
    candidate, obligation, receipt = _verified_candidate(dependency_result, verification_service)
    graph = target_graph()
    result = CandidatePromotionService().promote(
        candidate=candidate,
        obligation=obligation,
        receipt=receipt,
        target_graph=graph,
        policy=CandidatePromotionPolicy(
            "promotion.map", "1", canonical_predicate="ARCH_DEPENDS_ON"
        ),
    )
    assert result.promoted
    assert graph.edges[0].relation_type == "ARCH_DEPENDS_ON"


def test_promotion_rejects_candidate_binding_mismatch(dependency_result, verification_service):
    candidate, obligation, receipt = _verified_candidate(dependency_result, verification_service)
    wrong = CandidateKnowledge.create(subject_id="prod", predicate="CALLS", object_id="exp")
    result = CandidatePromotionService().promote(
        candidate=wrong,
        obligation=obligation,
        receipt=receipt,
        target_graph=target_graph(),
        policy=CandidatePromotionPolicy("promotion.default", "1"),
    )
    assert not result.promoted
    assert result.reason == "candidate_binding_mismatch"


def test_promotion_rejects_unapproved_verifier(dependency_result, verification_service):
    candidate, obligation, receipt = _verified_candidate(dependency_result, verification_service)
    result = CandidatePromotionService().promote(
        candidate=candidate,
        obligation=obligation,
        receipt=receipt,
        target_graph=target_graph(),
        policy=CandidatePromotionPolicy(
            "promotion.restricted", "1", allowed_verifier_ids=("different-verifier",)
        ),
    )
    assert not result.promoted
    assert result.reason == "verifier_not_allowed"


def test_promotion_rejects_missing_endpoint(dependency_result, verification_service):
    candidate, obligation, receipt = _verified_candidate(dependency_result, verification_service)
    graph = SemanticGraph()
    graph.add_node(SemanticNode("prod", "Module"))
    result = CandidatePromotionService().promote(
        candidate=candidate,
        obligation=obligation,
        receipt=receipt,
        target_graph=graph,
        policy=CandidatePromotionPolicy("promotion.default", "1"),
    )
    assert not result.promoted
    assert result.reason == "canonical_endpoint_missing"


def test_promotion_prevents_duplicate_relationship(dependency_result, verification_service):
    candidate, obligation, receipt = _verified_candidate(dependency_result, verification_service)
    graph = target_graph()
    service = CandidatePromotionService()
    policy = CandidatePromotionPolicy("promotion.default", "1")
    first = service.promote(candidate=candidate, obligation=obligation, receipt=receipt, target_graph=graph, policy=policy)
    second = service.promote(candidate=candidate, obligation=obligation, receipt=receipt, target_graph=graph, policy=policy)
    assert first.promoted
    assert not second.promoted
    assert second.reason == "canonical_relationship_already_exists"


def test_promotion_policy_can_require_validated_evidence(dependency_result, verification_service):
    candidate, obligation, receipt = _verified_candidate(dependency_result, verification_service)
    assert receipt.evidence_state is VerificationStatus.VALIDATED
    policy = CandidatePromotionPolicy(
        "promotion.validated", "1", minimum_evidence_state=VerificationStatus.VALIDATED
    )
    assert CandidatePromotionService().promote(
        candidate=candidate,
        obligation=obligation,
        receipt=receipt,
        target_graph=target_graph(),
        policy=policy,
    ).promoted
