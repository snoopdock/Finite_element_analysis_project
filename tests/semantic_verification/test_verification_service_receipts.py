
from dataclasses import replace

import pytest

from audit_engine.semantic_audit.graph.analysis import SemanticContext, VerificationStatus
from audit_engine.semantic_audit.verification import (
    EvidenceCorroborationVerifier,
    ObservationContractVerifier,
    VerificationAttempt,
    VerificationDecision,
    VerificationObligation,
    VerificationReceipt,
    VerificationService,
    VerifierRegistry,
)


def _registry():
    registry = VerifierRegistry()
    registry.register(ObservationContractVerifier())
    registry.register(EvidenceCorroborationVerifier())
    return registry


def _contract_obligation(result):
    return VerificationObligation.from_analysis_result(
        result,
        obligation_type="observation_contract",
        requested_verifier_ids=["observation-contract"],
        parameters={"subject_id": "A", "predicate": "DEPENDS_ON", "object_id": "B"},
    )


def test_registry_rejects_duplicate_verifier():
    registry = VerifierRegistry()
    registry.register(ObservationContractVerifier())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(ObservationContractVerifier())


def test_registry_resolves_requested_verifier(dependency_result):
    obligation = _contract_obligation(dependency_result)
    assert _registry().resolve(obligation).descriptor.verifier_id == "observation-contract"


def test_service_produces_immutable_receipt_binding(dependency_result):
    obligation = _contract_obligation(dependency_result)
    receipt = VerificationService(_registry()).verify(obligation, dependency_result)
    assert receipt.decision is VerificationDecision.CONFIRMED
    assert receipt.evidence_state is VerificationStatus.VALIDATED
    assert receipt.graph_fingerprint == dependency_result.graph_fingerprint
    assert receipt.semantic_context_fingerprint == dependency_result.semantic_context.fingerprint
    assert receipt.receipt_id.startswith("verification-receipt:")


def test_receipt_identity_is_deterministic(dependency_result):
    obligation = _contract_obligation(dependency_result)
    service = VerificationService(_registry())
    first = service.verify(obligation, dependency_result)
    second = service.verify(obligation, dependency_result)
    assert first.receipt_id == second.receipt_id


def test_receipt_detects_graph_staleness(dependency_result):
    obligation = _contract_obligation(dependency_result)
    receipt = VerificationService(_registry()).verify(obligation, dependency_result)
    assert receipt.is_stale_for(
        graph_fingerprint="graph:new",
        semantic_context_fingerprint=receipt.semantic_context_fingerprint,
    )


def test_receipt_detects_semantic_context_staleness(dependency_result):
    obligation = _contract_obligation(dependency_result)
    receipt = VerificationService(_registry()).verify(obligation, dependency_result)
    other = SemanticContext(relationship_vocabulary_version="relations/v2")
    assert receipt.is_stale_for(
        graph_fingerprint=receipt.graph_fingerprint,
        semantic_context_fingerprint=other.fingerprint,
    )


def test_receipt_rejects_attempt_with_foreign_evidence(dependency_result):
    obligation = _contract_obligation(dependency_result)
    attempt = VerificationAttempt.create(
        obligation_id=obligation.obligation_id,
        verifier_id="observation-contract",
        verifier_version="1.0.0",
        decision=VerificationDecision.CONFIRMED,
        evidence_state=VerificationStatus.VALIDATED,
        evidence_ids=["foreign:evidence"],
    )
    with pytest.raises(ValueError, match="outside its obligation"):
        VerificationReceipt.seal(obligation, attempt)


def test_service_rejects_verifier_not_allowed_by_obligation(dependency_result):
    obligation = _contract_obligation(dependency_result)
    with pytest.raises(ValueError, match="not permitted"):
        VerificationService(_registry()).verify(
            obligation, dependency_result, verifier_id="evidence-corroboration"
        )


def test_receipt_details_mapping_is_immutable(dependency_result):
    obligation = _contract_obligation(dependency_result)
    receipt = VerificationService(_registry()).verify(obligation, dependency_result)
    with pytest.raises(TypeError):
        receipt.details["mutate"] = True
