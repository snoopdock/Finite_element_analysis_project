"""Independent validation of solver certificates for G3.4.2.

A producing solver never gets to declare its own evidence ``VALIDATED``.  This
module checks certificates using repository-owned logic.  The first supported
forms are intentionally narrow:

* SAT model: independently evaluate the supplied assignment against the CNF.
* bounded UNSAT claim: independently exhaust the assignment space when the CNF
  is within the configured validation bound.

External UNSAT claims above that bound remain observed solver output until a
future proof checker (for example DRAT/LRAT or SMT proof validation) exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Any, Mapping, Sequence

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus

from .cnf_solver import cnf_true
from .models import ValidationCompleteness, VerificationWitness, WitnessKind


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


def validate_unsat_claim(
    *,
    certificate: Mapping[str, Any] | None,
    variable_count: int,
    clauses: Sequence[Sequence[int]],
    subject_digest: str,
    independent_max_variables: int = DEFAULT_INDEPENDENT_UNSAT_MAX_VARIABLES,
) -> SolverCertificateValidation:
    if independent_max_variables < 1:
        raise ValueError("independent_max_variables must be positive")
    certificate_kind = certificate.get("kind") if certificate is not None else None
    if certificate_kind not in {None, "unsat_claim", "unsupported_proof"}:
        return SolverCertificateValidation(
            established_verdict=None,
            evidence_state=VerificationStatus.REJECTED,
            completeness=ValidationCompleteness.PARTIAL,
            witness=None,
            diagnostics=(f"unsupported_unsat_certificate_kind:{certificate_kind}",),
            certificate_accepted=False,
        )

    if variable_count > independent_max_variables:
        # The external verdict is an observation, not a validated fact.  No
        # unimplemented proof format is silently trusted.
        return SolverCertificateValidation(
            established_verdict="unsat",
            evidence_state=VerificationStatus.OBSERVED,
            completeness=ValidationCompleteness.PARTIAL,
            witness=None,
            diagnostics=(
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
                diagnostics=("external_unsat_refuted_by_independent_model",),
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
        diagnostics=("external_unsat_independently_validated",),
        certificate_accepted=True,
    )


def validate_external_cnf_certificate(
    *,
    verdict: str,
    certificate: Mapping[str, Any] | None,
    variable_count: int,
    clauses: Sequence[Sequence[int]],
    subject_digest: str,
    independent_unsat_max_variables: int = DEFAULT_INDEPENDENT_UNSAT_MAX_VARIABLES,
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
