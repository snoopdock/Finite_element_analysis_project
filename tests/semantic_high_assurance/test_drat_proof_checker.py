from __future__ import annotations

from audit_engine.semantic_audit.high_assurance import (
    DRAT_PROOF_FORMAT,
    DratProofCheckLimits,
    DratUnsatProofChecker,
    RUP_PROOF_FORMAT,
    builtin_unsat_proof_checker_registry,
    validate_external_cnf_certificate,
)
from audit_engine.semantic_audit.high_assurance.cnf_solver import cnf_digest
from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.high_assurance.models import ValidationCompleteness


def _certificate(digest: str, steps):
    return {
        "kind": "unsat_proof",
        "proof_format": DRAT_PROOF_FORMAT,
        "cnf_digest": digest,
        "steps": steps,
    }


def test_drat_checker_accepts_empty_clause_rup_derivation():
    clauses = ((1,), (-1,))
    digest = cnf_digest(2, clauses)
    result = DratUnsatProofChecker().check(
        certificate=_certificate(digest, [{"op": "add", "clause": []}]),
        variable_count=2,
        clauses=clauses,
        subject_digest=digest,
    )
    assert result.accepted
    assert result.witness is not None
    assert result.witness.details["rup_additions"] == 1
    assert result.witness.details["rat_additions"] == 0


def test_drat_checker_accepts_genuine_non_rup_rat_step():
    # XOR-style contradiction is UNSAT but unit propagation has no initial
    # conflict.  Clause (x3) is therefore not RUP, while it is vacuously RAT
    # because the active formula contains no clause with !x3.
    clauses = ((1, 2), (-1, 2), (1, -2), (-1, -2))
    digest = cnf_digest(3, clauses)
    result = DratUnsatProofChecker().check(
        certificate=_certificate(
            digest,
            [
                {"op": "add", "clause": [3]},
                {"op": "add", "clause": [1]},
                {"op": "add", "clause": [-1]},
                {"op": "add", "clause": []},
            ],
        ),
        variable_count=3,
        clauses=clauses,
        subject_digest=digest,
    )
    assert result.accepted
    assert result.witness is not None
    assert result.witness.details["rat_additions"] == 1
    assert result.witness.details["rup_additions"] == 3



def test_drat_checker_accepts_non_vacuous_rat_step_with_rup_resolvent():
    # This UNSAT formula has no unit-propagation conflict initially.  Clause
    # (!x3) is not RUP, and x3 occurs in the active formula, so RAT is genuinely
    # non-vacuous.  Its resolvent obligations are RUP, after which the empty
    # clause becomes RUP.
    clauses = ((1, 2), (1, 3), (1, -2), (2, -1), (-1, -2))
    digest = cnf_digest(3, clauses)
    result = DratUnsatProofChecker().check(
        certificate=_certificate(
            digest,
            [
                {"op": "add", "clause": [-3]},
                {"op": "add", "clause": []},
            ],
        ),
        variable_count=3,
        clauses=clauses,
        subject_digest=digest,
    )
    assert result.accepted
    assert result.witness is not None
    assert result.witness.details["rat_additions"] == 1
    assert result.witness.details["rat_resolvents_checked"] >= 1
    assert result.witness.details["rup_additions"] == 1

def test_drat_checker_accepts_strict_deletion_of_present_clause():
    clauses = ((1,), (-1,))
    digest = cnf_digest(2, clauses)
    result = DratUnsatProofChecker().check(
        certificate=_certificate(
            digest,
            [
                {"op": "add", "clause": [2]},
                {"op": "delete", "clause": [2]},
                {"op": "add", "clause": []},
            ],
        ),
        variable_count=2,
        clauses=clauses,
        subject_digest=digest,
    )
    assert result.accepted
    assert result.witness is not None
    assert result.witness.details["deletions"] == 1


def test_drat_checker_rejects_deletion_of_missing_clause():
    clauses = ((1,), (-1,))
    digest = cnf_digest(2, clauses)
    result = DratUnsatProofChecker().check(
        certificate=_certificate(
            digest,
            [
                {"op": "delete", "clause": [2]},
                {"op": "add", "clause": []},
            ],
        ),
        variable_count=2,
        clauses=clauses,
        subject_digest=digest,
    )
    assert not result.accepted
    assert result.diagnostics == ("drat_delete_missing_clause:1",)


def test_drat_checker_rejects_invalid_rat_step():
    # Candidate (x2) has pivot x2.  The opposing clause (!x2 v x3)
    # creates resolvent (x3), which is not RUP from this formula.
    clauses = ((-2, 3),)
    digest = cnf_digest(3, clauses)
    result = DratUnsatProofChecker().check(
        certificate=_certificate(
            digest,
            [
                {"op": "add", "clause": [2]},
                {"op": "add", "clause": []},
            ],
        ),
        variable_count=3,
        clauses=clauses,
        subject_digest=digest,
    )
    assert not result.accepted
    assert result.diagnostics == ("drat_rat_step_failed:1",)


def test_drat_checker_uses_first_literal_as_rat_pivot():
    # Reordering is semantically equivalent as a clause but changes the DRAT
    # pivot.  The checker preserves proof literal order rather than sorting it.
    clauses = ((-2, 3),)
    digest = cnf_digest(3, clauses)
    result = DratUnsatProofChecker().check(
        certificate=_certificate(
            digest,
            [
                {"op": "add", "clause": [1, 2]},  # pivot x1; no !x1 clauses => RAT
                {"op": "delete", "clause": [2, 1]},  # semantic deletion ignores order
                {"op": "add", "clause": [4]},
                {"op": "delete", "clause": [4]},
                {"op": "add", "clause": []},
            ],
        ),
        variable_count=4,
        clauses=((1,), (-1,)),  # override below? kept contradictory for final RUP
        subject_digest=cnf_digest(4, ((1,), (-1,))),
    )
    # Certificate digest above intentionally mismatches the supplied formula.
    assert not result.accepted
    assert result.diagnostics == ("drat_certificate_cnf_digest_mismatch",)


def test_drat_checker_preserves_pivot_order_on_valid_proof():
    clauses = ((1, 2), (-1, 2), (1, -2), (-1, -2))
    digest = cnf_digest(4, clauses)
    result = DratUnsatProofChecker().check(
        certificate=_certificate(
            digest,
            [
                {"op": "add", "clause": [4, 3]},  # pivot x4; no !x4 clauses
                {"op": "delete", "clause": [3, 4]},
                {"op": "add", "clause": [1]},
                {"op": "add", "clause": [-1]},
                {"op": "add", "clause": []},
            ],
        ),
        variable_count=4,
        clauses=clauses,
        subject_digest=digest,
    )
    assert result.accepted
    assert result.witness is not None
    assert result.witness.details["rat_additions"] == 1

def test_drat_checker_rejects_unknown_step_fields():
    clauses = ((1,), (-1,))
    digest = cnf_digest(1, clauses)
    result = DratUnsatProofChecker().check(
        certificate=_certificate(
            digest,
            [{"op": "add", "clause": [], "trusted": True}],
        ),
        variable_count=1,
        clauses=clauses,
        subject_digest=digest,
    )
    assert not result.accepted
    assert result.diagnostics[0].startswith("invalid_drat_certificate:")


def test_drat_checker_rejects_wrong_cnf_digest():
    clauses = ((1,), (-1,))
    digest = cnf_digest(1, clauses)
    result = DratUnsatProofChecker().check(
        certificate=_certificate("0" * 64, [{"op": "add", "clause": []}]),
        variable_count=1,
        clauses=clauses,
        subject_digest=digest,
    )
    assert not result.accepted
    assert result.diagnostics == ("drat_certificate_cnf_digest_mismatch",)


def test_drat_checker_requires_added_empty_clause_as_final_step():
    clauses = ((1,), (-1,))
    digest = cnf_digest(2, clauses)
    result = DratUnsatProofChecker().check(
        certificate=_certificate(digest, [{"op": "add", "clause": [2]}]),
        variable_count=2,
        clauses=clauses,
        subject_digest=digest,
    )
    assert not result.accepted
    assert result.diagnostics == ("drat_proof_must_end_with_added_empty_clause",)


def test_drat_resource_limit_is_rejection_not_semantic_counterclaim():
    clauses = ((1,), (-1,))
    digest = cnf_digest(3, clauses)
    checker = DratUnsatProofChecker(limits=DratProofCheckLimits(max_steps=1))
    result = checker.check(
        certificate=_certificate(
            digest,
            [
                {"op": "add", "clause": [2]},
                {"op": "add", "clause": []},
            ],
        ),
        variable_count=3,
        clauses=clauses,
        subject_digest=digest,
    )
    assert not result.accepted
    assert result.diagnostics == ("drat_resource_limit:step_limit",)


def test_builtin_registry_exposes_rup_and_drat_explicitly():
    formats = builtin_unsat_proof_checker_registry().formats()
    assert formats == tuple(sorted((RUP_PROOF_FORMAT, DRAT_PROOF_FORMAT)))


def test_external_certificate_validation_accepts_valid_drat_unsat():
    clauses = ((1,), (-1,))
    digest = cnf_digest(13, clauses)
    result = validate_external_cnf_certificate(
        verdict="unsat",
        certificate=_certificate(
            digest,
            [
                {"op": "add", "clause": [2]},
                {"op": "delete", "clause": [2]},
                {"op": "add", "clause": []},
            ],
        ),
        variable_count=13,
        clauses=clauses,
        subject_digest=digest,
        independent_unsat_max_variables=12,
    )
    assert result.certificate_accepted
    assert result.evidence_state == VerificationStatus.VALIDATED
    assert result.completeness == ValidationCompleteness.CERTIFICATE_COMPLETE_WITHIN_SCOPE


def test_external_certificate_validation_does_not_promote_invalid_large_drat():
    clauses = ((-2, 3),)
    digest = cnf_digest(13, clauses)
    result = validate_external_cnf_certificate(
        verdict="unsat",
        certificate=_certificate(
            digest,
            [
                {"op": "add", "clause": [2]},
                {"op": "add", "clause": []},
            ],
        ),
        variable_count=13,
        clauses=clauses,
        subject_digest=digest,
        independent_unsat_max_variables=12,
    )
    assert not result.certificate_accepted
    assert result.evidence_state == VerificationStatus.OBSERVED
    assert result.completeness == ValidationCompleteness.PARTIAL
