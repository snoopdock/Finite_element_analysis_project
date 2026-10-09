from __future__ import annotations

import pytest

from audit_engine.semantic_audit.high_assurance import (
    ProofCheckLimits,
    RUP_PROOF_FORMAT,
    RupUnsatProofChecker,
    UnsatProofCheckerRegistry,
    clause_is_rup,
)
from audit_engine.semantic_audit.high_assurance.cnf_solver import cnf_digest


def certificate(variable_count, clauses, steps):
    return {
        "kind": "unsat_proof",
        "proof_format": RUP_PROOF_FORMAT,
        "cnf_digest": cnf_digest(variable_count, clauses),
        "steps": steps,
    }


def test_direct_unit_contradiction_accepts_empty_clause_rup_proof():
    clauses = ((1,), (-1,))
    result = RupUnsatProofChecker().check(
        certificate=certificate(13, clauses, [[]]),
        variable_count=13,
        clauses=clauses,
        subject_digest=cnf_digest(13, clauses),
    )
    assert result.accepted is True
    assert result.checked_steps == 1
    assert result.witness.details["final_empty_clause"] is True


def test_multistep_rup_proof_can_derive_units_before_empty_clause():
    clauses = ((1, 2), (-1, 2), (1, -2), (-1, -2))
    result = RupUnsatProofChecker().check(
        certificate=certificate(2, clauses, [[1], [-1], []]),
        variable_count=2,
        clauses=clauses,
        subject_digest=cnf_digest(2, clauses),
    )
    assert result.accepted is True
    assert result.checked_steps == 3
    assert result.witness.details["proof_steps"] == 3


def test_empty_clause_is_not_rup_when_unit_propagation_has_no_conflict():
    formula = ((1, 2), (-1, 2), (1, -2), (-1, -2))
    assert clause_is_rup((), formula=formula) is False


def test_invalid_rup_step_is_rejected_at_exact_step():
    clauses = ((1, 2), (-1, 2), (1, -2), (-1, -2))
    result = RupUnsatProofChecker().check(
        certificate=certificate(2, clauses, [[]]),
        variable_count=2,
        clauses=clauses,
        subject_digest=cnf_digest(2, clauses),
    )
    assert result.accepted is False
    assert result.diagnostics == ("rup_step_failed:1",)


def test_rup_proof_must_end_in_empty_clause():
    clauses = ((1,), (-1,))
    result = RupUnsatProofChecker().check(
        certificate=certificate(1, clauses, [[1]]),
        variable_count=1,
        clauses=clauses,
        subject_digest=cnf_digest(1, clauses),
    )
    assert result.accepted is False
    assert result.diagnostics == ("rup_proof_must_end_with_empty_clause",)


def test_rup_certificate_is_bound_to_exact_cnf_digest():
    clauses = ((1,), (-1,))
    cert = certificate(1, clauses, [[]])
    cert["cnf_digest"] = "0" * 64
    result = RupUnsatProofChecker().check(
        certificate=cert,
        variable_count=1,
        clauses=clauses,
        subject_digest=cnf_digest(1, clauses),
    )
    assert result.accepted is False
    assert result.diagnostics == ("rup_certificate_cnf_digest_mismatch",)


def test_rup_checker_rejects_literal_outside_declared_variables():
    clauses = ((1,), (-1,))
    result = RupUnsatProofChecker().check(
        certificate=certificate(1, clauses, [[2], []]),
        variable_count=1,
        clauses=clauses,
        subject_digest=cnf_digest(1, clauses),
    )
    assert result.accepted is False
    assert result.diagnostics[0].startswith("invalid_rup_certificate:")


def test_rup_checker_enforces_step_limit_before_checking():
    clauses = ((1,), (-1,))
    checker = RupUnsatProofChecker(limits=ProofCheckLimits(max_steps=1))
    result = checker.check(
        certificate=certificate(1, clauses, [[1], []]),
        variable_count=1,
        clauses=clauses,
        subject_digest=cnf_digest(1, clauses),
    )
    assert result.accepted is False
    assert result.diagnostics == ("rup_certificate_exceeds_step_limit",)


def test_rup_checker_enforces_total_literal_limit():
    clauses = ((1,), (-1,))
    checker = RupUnsatProofChecker(limits=ProofCheckLimits(max_total_literals=1))
    result = checker.check(
        certificate=certificate(1, clauses, [[1], [-1], []]),
        variable_count=1,
        clauses=clauses,
        subject_digest=cnf_digest(1, clauses),
    )
    assert result.accepted is False
    assert result.diagnostics == ("rup_certificate_exceeds_literal_limit",)


def test_rup_checker_enforces_clause_width_limit():
    clauses = ((1,), (-1,))
    checker = RupUnsatProofChecker(limits=ProofCheckLimits(max_clause_width=1))
    result = checker.check(
        certificate=certificate(2, clauses, [[1, 2], []]),
        variable_count=2,
        clauses=clauses,
        subject_digest=cnf_digest(2, clauses),
    )
    assert result.accepted is False
    assert "width limit" in result.diagnostics[0]


def test_tautological_clause_is_rup_because_negated_assumptions_conflict():
    assert clause_is_rup((1, -1), formula=((2,),)) is True


def test_proof_checker_registry_rejects_duplicate_format():
    registry = UnsatProofCheckerRegistry()
    registry.register(RupUnsatProofChecker())
    with pytest.raises(ValueError, match="Duplicate UNSAT proof checker"):
        registry.register(RupUnsatProofChecker())


def test_proof_check_result_serializes_without_embedding_raw_proof():
    clauses = ((1,), (-1,))
    result = RupUnsatProofChecker().check(
        certificate=certificate(1, clauses, [[]]),
        variable_count=1,
        clauses=clauses,
        subject_digest=cnf_digest(1, clauses),
    )
    payload = result.to_dict()
    assert payload["accepted"] is True
    assert payload["witness_id"] == result.witness.witness_id
    assert "steps" not in payload


def test_rup_certificate_rejects_unknown_fields_in_runtime_not_only_schema():
    clauses = ((1,), (-1,))
    cert = certificate(1, clauses, [[]])
    cert["trusted"] = True
    result = RupUnsatProofChecker().check(
        certificate=cert,
        variable_count=1,
        clauses=clauses,
        subject_digest=cnf_digest(1, clauses),
    )
    assert result.accepted is False
    assert result.diagnostics[0].startswith("rup_certificate_unknown_fields:")
