
from audit_engine.semantic_audit.graph.analysis import VerificationStatus
from audit_engine.semantic_audit.verification import (
    ObservationContractVerifier,
    VerificationContext,
    VerificationDecision,
    VerificationObligation,
)


def _obligation(result, **params):
    return VerificationObligation.from_analysis_result(
        result,
        obligation_type="observation_contract",
        requested_verifier_ids=["observation-contract"],
        parameters=params,
    )


def test_contract_verifier_confirms_matching_observation(dependency_result):
    obligation = _obligation(
        dependency_result,
        subject_id="A",
        predicate="DEPENDS_ON",
        object_id="B",
    )
    attempt = ObservationContractVerifier().verify(
        obligation, VerificationContext(dependency_result)
    )
    assert attempt.decision is VerificationDecision.CONFIRMED
    assert attempt.evidence_state is VerificationStatus.VALIDATED
    assert attempt.details["matched_observation_ids"]


def test_contract_verifier_refutes_nonmatching_observation(dependency_result):
    obligation = _obligation(
        dependency_result,
        subject_id="A",
        predicate="CALLS",
        object_id="B",
    )
    attempt = ObservationContractVerifier().verify(
        obligation, VerificationContext(dependency_result)
    )
    assert attempt.decision is VerificationDecision.REFUTED
    assert attempt.evidence_state is VerificationStatus.VALIDATED


def test_contract_verifier_is_inconclusive_without_expected_fields(dependency_result):
    obligation = _obligation(dependency_result)
    attempt = ObservationContractVerifier().verify(
        obligation, VerificationContext(dependency_result)
    )
    assert attempt.decision is VerificationDecision.INCONCLUSIVE
    assert attempt.evidence_state is VerificationStatus.INCONCLUSIVE


def test_contract_verifier_can_check_predicate_only(dependency_result):
    obligation = _obligation(dependency_result, predicate="DEPENDS_ON")
    attempt = ObservationContractVerifier().verify(
        obligation, VerificationContext(dependency_result)
    )
    assert attempt.decision is VerificationDecision.CONFIRMED
