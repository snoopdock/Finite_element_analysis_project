"""Independent validation of solver certificates for G3.4.x.

A producing solver never gets to declare its own evidence ``VALIDATED``.  This
module checks certificates using repository-owned logic.  Supported forms are:

* SAT model: independently evaluate the supplied assignment against the CNF.
* bounded UNSAT claim: independently exhaust the assignment space when the CNF
  is within the configured validation bound.
* proof-carrying UNSAT: dispatch an explicitly supported proof format to a
  repository-owned checker.  G3.4.3 ships an addition-only RUP checker.

Unsupported or invalid external proofs remain solver observations unless a
separate repository-owned validation path independently establishes a verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Any, Mapping, Sequence

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus

from .cnf_solver import cnf_true
from .models import ValidationCompleteness, VerificationWitness, WitnessKind
from .unsat_proof import UnsatProofCheckerRegistry, builtin_unsat_proof_checker_registry


DEFAULT_INDEPENDENT_UNSAT_MAX_VARIABLES = 12


@dataclass(frozen=True)
class SolverCertificateValidation:
    established_verdict: str | None
    evidence_state: VerificationStatus
    completeness: ValidationCompleteness
    witness: VerificationWitness | None
    diagnostics: tuple[str, ...]
    certificate_accepted: bool


def _normalize_assignment(raw: object, variable_count: int) -> tuple[bool, ...]:
    if not isinstance(raw, Mapping):
        raise ValueError("SAT certificate assignment must be an object")
    expected_keys = {str(index) for index in range(1, variable_count + 1)}
    if set(str(key) for key in raw) != expected_keys:
        raise ValueError("SAT certificate assignment must bind every declared variable exactly once")
    values: list[bool] = []
    for index in range(1, variable_count + 1):
        value = raw.get(str(index))
        if not isinstance(value, bool):
            raise ValueError("SAT certificate assignment values must be boolean")
        values.append(value)
    return tuple(values)


def validate_sat_model_certificate(
    *,
    certificate: Mapping[str, Any] | None,
    variable_count: int,
    clauses: Sequence[Sequence[int]],
    subject_digest: str,
) -> SolverCertificateValidation:
    if certificate is None or certificate.get("kind") != "sat_model":
        return SolverCertificateValidation(
            established_verdict=None,
            evidence_state=VerificationStatus.REJECTED,
            completeness=ValidationCompleteness.PARTIAL,
            witness=None,
            diagnostics=("missing_or_unsupported_sat_certificate",),
            certificate_accepted=False,
        )
    try:
        assignment = _normalize_assignment(certificate.get("assignment"), variable_count)
    except ValueError as exc:
        return SolverCertificateValidation(
            established_verdict=None,
            evidence_state=VerificationStatus.REJECTED,
            completeness=ValidationCompleteness.PARTIAL,
            witness=None,
            diagnostics=(f"invalid_sat_certificate:{exc}",),
            certificate_accepted=False,
        )
    if not cnf_true(clauses, assignment):
        return SolverCertificateValidation(
            established_verdict=None,
            evidence_state=VerificationStatus.REJECTED,
            completeness=ValidationCompleteness.PARTIAL,
            witness=None,
            diagnostics=("sat_certificate_assignment_does_not_satisfy_cnf",),
            certificate_accepted=False,
        )
    normalized = {str(index + 1): value for index, value in enumerate(assignment)}
    witness = VerificationWitness.create(
        kind=WitnessKind.SOLVER_CERTIFICATE,
        subject_digest=subject_digest,
        summary="External SAT model was independently checked against every CNF clause.",
        reproducible=True,
        details={
            "certificate_kind": "sat_model",
            "assignment": normalized,
            "certificate_validation": "independent_clause_evaluation",
            "cnf_digest": subject_digest,
        },
    )
    return SolverCertificateValidation(
        established_verdict="sat",
        evidence_state=VerificationStatus.VALIDATED,
        completeness=ValidationCompleteness.CERTIFICATE_COMPLETE_WITHIN_SCOPE,
        witness=witness,
        diagnostics=("sat_model_certificate_valid",),
        certificate_accepted=True,
    )


def _validate_unsat_by_bounded_enumeration(
    *,
    variable_count: int,
    clauses: Sequence[Sequence[int]],
    subject_digest: str,
    independent_max_variables: int,
    diagnostic_prefix: tuple[str, ...] = (),
) -> SolverCertificateValidation:
    if variable_count > independent_max_variables:
        return SolverCertificateValidation(
            established_verdict="unsat",
            evidence_state=VerificationStatus.OBSERVED,
            completeness=ValidationCompleteness.PARTIAL,
            witness=None,
            diagnostics=diagnostic_prefix
            + (
                "external_unsat_observed_but_not_independently_validated",
                f"independent_unsat_bound={independent_max_variables}",
            ),
            certificate_accepted=False,
        )

    checked = 0
    for assignment in product((False, True), repeat=variable_count):
        checked += 1
        if cnf_true(clauses, assignment):
            counterexample = {str(index + 1): value for index, value in enumerate(assignment)}
            witness = VerificationWitness.create(
                kind=WitnessKind.COUNTEREXAMPLE,
                subject_digest=subject_digest,
                summary="Independent bounded validation found a model contradicting external UNSAT.",
                reproducible=True,
                details={
                    "certificate_kind": "unsat_claim",
                    "counterexample_assignment": counterexample,
                    "checked_assignments_before_counterexample": checked,
                    "cnf_digest": subject_digest,
                },
            )
            return SolverCertificateValidation(
                established_verdict="sat",
                evidence_state=VerificationStatus.VALIDATED,
                completeness=ValidationCompleteness.CERTIFICATE_COMPLETE_WITHIN_SCOPE,
                witness=witness,
                diagnostics=diagnostic_prefix + ("external_unsat_refuted_by_independent_model",),
                certificate_accepted=False,
            )

    witness = VerificationWitness.create(
        kind=WitnessKind.SOLVER_CERTIFICATE,
        subject_digest=subject_digest,
        summary="External UNSAT claim was independently validated by exhaustive bounded enumeration.",
        reproducible=True,
        details={
            "certificate_kind": "independently_validated_unsat",
            "checked_assignments": checked,
            "total_assignments": 2 ** variable_count,
            "certificate_validation": "independent_truth_table_exhaustion",
            "cnf_digest": subject_digest,
        },
    )
    return SolverCertificateValidation(
        established_verdict="unsat",
        evidence_state=VerificationStatus.VALIDATED,
        completeness=ValidationCompleteness.EXHAUSTIVE_WITHIN_SCOPE,
        witness=witness,
        diagnostics=diagnostic_prefix + ("external_unsat_independently_validated",),
        certificate_accepted=True,
    )


def _validate_unsat_proof_certificate(
    *,
    certificate: Mapping[str, Any],
    variable_count: int,
    clauses: Sequence[Sequence[int]],
    subject_digest: str,
    proof_checker_registry: UnsatProofCheckerRegistry,
) -> SolverCertificateValidation:
    raw_format = certificate.get("proof_format")
    if not isinstance(raw_format, str) or not raw_format.strip():
        return SolverCertificateValidation(
            established_verdict="unsat",
            evidence_state=VerificationStatus.OBSERVED,
            completeness=ValidationCompleteness.PARTIAL,
            witness=None,
            diagnostics=("unsat_proof_missing_proof_format",),
            certificate_accepted=False,
        )
    checker = proof_checker_registry.get(raw_format)
    if checker is None:
        return SolverCertificateValidation(
            established_verdict="unsat",
            evidence_state=VerificationStatus.OBSERVED,
            completeness=ValidationCompleteness.PARTIAL,
            witness=None,
            diagnostics=(f"unsupported_unsat_proof_format:{raw_format}",),
            certificate_accepted=False,
        )
    checked = checker.check(
        certificate=certificate,
        variable_count=variable_count,
        clauses=clauses,
        subject_digest=subject_digest,
    )
    if not checked.accepted:
        return SolverCertificateValidation(
            established_verdict="unsat",
            evidence_state=VerificationStatus.OBSERVED,
            completeness=ValidationCompleteness.PARTIAL,
            witness=None,
            diagnostics=checked.diagnostics + ("external_unsat_proof_not_accepted",),
            certificate_accepted=False,
        )
    return SolverCertificateValidation(
        established_verdict="unsat",
        evidence_state=VerificationStatus.VALIDATED,
        completeness=ValidationCompleteness.CERTIFICATE_COMPLETE_WITHIN_SCOPE,
        witness=checked.witness,
        diagnostics=checked.diagnostics + ("external_unsat_proof_independently_validated",),
        certificate_accepted=True,
    )


def validate_unsat_claim(
    *,
    certificate: Mapping[str, Any] | None,
    variable_count: int,
    clauses: Sequence[Sequence[int]],
    subject_digest: str,
    independent_max_variables: int = DEFAULT_INDEPENDENT_UNSAT_MAX_VARIABLES,
    proof_checker_registry: UnsatProofCheckerRegistry | None = None,
) -> SolverCertificateValidation:
    if independent_max_variables < 1:
        raise ValueError("independent_max_variables must be positive")
    certificate_kind = certificate.get("kind") if certificate is not None else None

    if certificate_kind == "unsat_proof":
        proof_result = _validate_unsat_proof_certificate(
            certificate=certificate,
            variable_count=variable_count,
            clauses=clauses,
            subject_digest=subject_digest,
            proof_checker_registry=proof_checker_registry or builtin_unsat_proof_checker_registry(),
        )
        if proof_result.certificate_accepted:
            return proof_result
        # A rejected/unsupported proof never becomes trusted.  For small CNFs,
        # however, an independent exhaustive checker can still establish the
        # semantic verdict without relying on the external proof.
        if variable_count <= independent_max_variables:
            return _validate_unsat_by_bounded_enumeration(
                variable_count=variable_count,
                clauses=clauses,
                subject_digest=subject_digest,
                independent_max_variables=independent_max_variables,
                diagnostic_prefix=proof_result.diagnostics,
            )
        return proof_result

    if certificate_kind not in {None, "unsat_claim", "unsupported_proof"}:
        return SolverCertificateValidation(
            established_verdict="unsat",
            evidence_state=VerificationStatus.OBSERVED,
            completeness=ValidationCompleteness.PARTIAL,
            witness=None,
            diagnostics=(f"unsupported_unsat_certificate_kind:{certificate_kind}",),
            certificate_accepted=False,
        )

    return _validate_unsat_by_bounded_enumeration(
        variable_count=variable_count,
        clauses=clauses,
        subject_digest=subject_digest,
        independent_max_variables=independent_max_variables,
    )


def validate_external_cnf_certificate(
    *,
    verdict: str,
    certificate: Mapping[str, Any] | None,
    variable_count: int,
    clauses: Sequence[Sequence[int]],
    subject_digest: str,
    independent_unsat_max_variables: int = DEFAULT_INDEPENDENT_UNSAT_MAX_VARIABLES,
    proof_checker_registry: UnsatProofCheckerRegistry | None = None,
) -> SolverCertificateValidation:
    if verdict == "sat":
        return validate_sat_model_certificate(
            certificate=certificate,
            variable_count=variable_count,
            clauses=clauses,
            subject_digest=subject_digest,
        )
    if verdict == "unsat":
        return validate_unsat_claim(
            certificate=certificate,
            variable_count=variable_count,
            clauses=clauses,
            subject_digest=subject_digest,
            independent_max_variables=independent_unsat_max_variables,
            proof_checker_registry=proof_checker_registry,
        )
    if verdict == "unknown":
        return SolverCertificateValidation(
            established_verdict=None,
            evidence_state=VerificationStatus.INCONCLUSIVE,
            completeness=ValidationCompleteness.PARTIAL,
            witness=None,
            diagnostics=("external_solver_returned_unknown",),
            certificate_accepted=False,
        )
    raise ValueError(f"Unsupported solver verdict: {verdict}")
