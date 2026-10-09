from __future__ import annotations

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.high_assurance.certificate_validation import (
    validate_external_cnf_certificate,
)
from audit_engine.semantic_audit.high_assurance.models import ValidationCompleteness, WitnessKind


def test_sat_model_certificate_is_independently_validated():
    result = validate_external_cnf_certificate(
        verdict="sat",
        certificate={"kind": "sat_model", "assignment": {"1": True, "2": False}},
        variable_count=2,
        clauses=((1,), (-2,)),
        subject_digest="a" * 64,
    )
    assert result.established_verdict == "sat"
    assert result.evidence_state == VerificationStatus.VALIDATED
    assert result.completeness == ValidationCompleteness.CERTIFICATE_COMPLETE_WITHIN_SCOPE
    assert result.certificate_accepted is True
    assert result.witness.kind == WitnessKind.SOLVER_CERTIFICATE


def test_invalid_sat_model_is_rejected_without_guessing_unsat():
    result = validate_external_cnf_certificate(
        verdict="sat",
        certificate={"kind": "sat_model", "assignment": {"1": False}},
        variable_count=1,
        clauses=((1,),),
        subject_digest="b" * 64,
    )
    assert result.established_verdict is None
    assert result.evidence_state == VerificationStatus.REJECTED
    assert result.certificate_accepted is False


def test_small_unsat_claim_is_independently_exhausted():
    result = validate_external_cnf_certificate(
        verdict="unsat",
        certificate={"kind": "unsat_claim"},
        variable_count=1,
        clauses=((1,), (-1,)),
        subject_digest="c" * 64,
    )
    assert result.established_verdict == "unsat"
    assert result.evidence_state == VerificationStatus.VALIDATED
    assert result.completeness == ValidationCompleteness.EXHAUSTIVE_WITHIN_SCOPE
    assert result.certificate_accepted is True
    assert result.witness.details["total_assignments"] == 2


def test_false_unsat_claim_yields_validated_counterexample():
    result = validate_external_cnf_certificate(
        verdict="unsat",
        certificate={"kind": "unsat_claim"},
        variable_count=1,
        clauses=((1,),),
        subject_digest="d" * 64,
    )
    assert result.established_verdict == "sat"
    assert result.evidence_state == VerificationStatus.VALIDATED
    assert result.certificate_accepted is False
    assert result.witness.kind == WitnessKind.COUNTEREXAMPLE


def test_large_unsat_without_proof_checker_remains_observed():
    result = validate_external_cnf_certificate(
        verdict="unsat",
        certificate={"kind": "unsat_claim"},
        variable_count=13,
        clauses=((1,), (-1,)),
        subject_digest="e" * 64,
        independent_unsat_max_variables=12,
    )
    assert result.established_verdict == "unsat"
    assert result.evidence_state == VerificationStatus.OBSERVED
    assert result.completeness == ValidationCompleteness.PARTIAL
    assert result.certificate_accepted is False
    assert result.witness is None


def test_unknown_solver_verdict_is_inconclusive():
    result = validate_external_cnf_certificate(
        verdict="unknown",
        certificate=None,
        variable_count=1,
        clauses=((1,),),
        subject_digest="f" * 64,
    )
    assert result.established_verdict is None
    assert result.evidence_state == VerificationStatus.INCONCLUSIVE


def test_large_valid_rup_proof_is_validated_without_bounded_enumeration():
    from audit_engine.semantic_audit.high_assurance.cnf_solver import cnf_digest

    clauses = ((1,), (-1,))
    digest = cnf_digest(13, clauses)
    result = validate_external_cnf_certificate(
        verdict="unsat",
        certificate={
            "kind": "unsat_proof",
            "proof_format": "cnf-rup/v1",
            "cnf_digest": digest,
            "steps": [[]],
        },
        variable_count=13,
        clauses=clauses,
        subject_digest=digest,
        independent_unsat_max_variables=12,
    )
    assert result.established_verdict == "unsat"
    assert result.evidence_state == VerificationStatus.VALIDATED
    assert result.completeness == ValidationCompleteness.CERTIFICATE_COMPLETE_WITHIN_SCOPE
    assert result.certificate_accepted is True
    assert result.witness.kind == WitnessKind.FORMAL_PROOF


def test_large_unsupported_unsat_proof_format_remains_observed():
    result = validate_external_cnf_certificate(
        verdict="unsat",
        certificate={
            "kind": "unsat_proof",
            "proof_format": "unknown-proof/v1",
            "cnf_digest": "f" * 64,
            "steps": [[]],
        },
        variable_count=13,
        clauses=((1,), (-1,)),
        subject_digest="f" * 64,
        independent_unsat_max_variables=12,
    )
    assert result.established_verdict == "unsat"
    assert result.evidence_state == VerificationStatus.OBSERVED
    assert result.completeness == ValidationCompleteness.PARTIAL
    assert result.certificate_accepted is False


def test_invalid_small_rup_proof_can_fall_back_to_independent_exhaustion():
    from audit_engine.semantic_audit.high_assurance.cnf_solver import cnf_digest

    clauses = ((1, 2), (-1, 2), (1, -2), (-1, -2))
    digest = cnf_digest(2, clauses)
    result = validate_external_cnf_certificate(
        verdict="unsat",
        certificate={
            "kind": "unsat_proof",
            "proof_format": "cnf-rup/v1",
            "cnf_digest": digest,
            "steps": [[]],
        },
        variable_count=2,
        clauses=clauses,
        subject_digest=digest,
        independent_unsat_max_variables=12,
    )
    assert result.established_verdict == "unsat"
    assert result.evidence_state == VerificationStatus.VALIDATED
    assert result.completeness == ValidationCompleteness.EXHAUSTIVE_WITHIN_SCOPE
    assert result.certificate_accepted is True
    assert "rup_step_failed:1" in result.diagnostics
    assert "external_unsat_independently_validated" in result.diagnostics
