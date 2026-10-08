
from audit_engine.semantic_audit.graph.analysis import VerificationStatus
from audit_engine.semantic_audit.verification import (
    EvidenceCorroborationVerifier,
    VerificationContext,
    VerificationDecision,
    VerificationObligation,
)


def test_corroboration_requires_explicit_independence_groups(dependency_result):
    obligation = VerificationObligation.from_analysis_result(
        dependency_result,
        obligation_type="evidence_corroboration",
        parameters={"independence_key": "source_id", "minimum_independent_sources": 2},
    )
    attempt = EvidenceCorroborationVerifier().verify(
        obligation, VerificationContext(dependency_result)
    )
    assert attempt.decision is VerificationDecision.CONFIRMED
    assert attempt.evidence_state is VerificationStatus.CORROBORATED
    assert attempt.details["independent_source_groups"] == ["source-1", "source-2"]


def test_corroboration_is_inconclusive_when_independence_not_proven(dependency_result):
    obligation = VerificationObligation.from_analysis_result(
        dependency_result,
        obligation_type="evidence_corroboration",
        parameters={"independence_key": "publisher", "minimum_independent_sources": 2},
    )
    attempt = EvidenceCorroborationVerifier().verify(
        obligation, VerificationContext(dependency_result)
    )
    assert attempt.decision is VerificationDecision.INCONCLUSIVE
    assert attempt.evidence_state is VerificationStatus.INCONCLUSIVE
    assert len(attempt.details["evidence_missing_independence_key"]) == 2


def test_corroboration_rejects_minimum_below_two(dependency_result):
    obligation = VerificationObligation.from_analysis_result(
        dependency_result,
        obligation_type="evidence_corroboration",
        parameters={"minimum_independent_sources": 1},
    )
    try:
        EvidenceCorroborationVerifier().verify(
            obligation, VerificationContext(dependency_result)
        )
    except ValueError as exc:
        assert "at least 2" in str(exc)
    else:
        raise AssertionError("minimum below two should fail")
