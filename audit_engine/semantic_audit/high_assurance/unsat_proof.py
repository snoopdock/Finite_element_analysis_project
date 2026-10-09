"""Repository-owned CNF UNSAT proof checking for G3.4.3.

The first supported proof format is a bounded addition-only RUP certificate.
Every added clause must satisfy reverse unit propagation (RUP) against the
original CNF plus previously accepted proof clauses, and the final proof step
must derive the empty clause.  This is intentionally narrower than DRUP/DRAT:
there are no deletion steps and no RAT inference.  The narrow contract keeps
the checker small, deterministic, auditable, and independent from the external
solver that produced the proof.

A successful check establishes UNSAT only for the exact CNF digest bound into
the certificate.  Resource limits are part of the validation envelope; hitting
one is an inconclusive proof check, never evidence that the formula is SAT.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping, Protocol, Sequence

from .models import VerificationWitness, WitnessKind


RUP_PROOF_FORMAT = "cnf-rup/v1"
RUP_CHECKER_ID = "repository-cnf-rup-checker"
RUP_CHECKER_VERSION = "1.0.0"


@dataclass(frozen=True)
class ProofCheckLimits:
    """Hard parser/checker bounds for untrusted proof certificates."""

    max_steps: int = 10_000
    max_total_literals: int = 250_000
    max_clause_width: int = 5_000

    def __post_init__(self) -> None:
        if min(self.max_steps, self.max_total_literals, self.max_clause_width) < 1:
            raise ValueError("Proof checker limits must be positive.")


@dataclass(frozen=True)
class UnsatProofCheckerDescriptor:
    checker_id: str
    version: str
    proof_format: str

    def __post_init__(self) -> None:
        if not self.checker_id.strip() or not self.version.strip() or not self.proof_format.strip():
            raise ValueError("UNSAT proof checker descriptor fields must be non-empty.")


@dataclass(frozen=True)
class UnsatProofCheckResult:
    accepted: bool
    proof_format: str
    checker_id: str
    checker_version: str
    proof_digest: str | None
    checked_steps: int
    total_proof_literals: int
    witness: VerificationWitness | None
    diagnostics: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "proof_format": self.proof_format,
            "checker_id": self.checker_id,
            "checker_version": self.checker_version,
            "proof_digest": self.proof_digest,
            "checked_steps": self.checked_steps,
            "total_proof_literals": self.total_proof_literals,
            "witness_id": self.witness.witness_id if self.witness is not None else None,
            "diagnostics": list(self.diagnostics),
        }


class UnsatProofChecker(Protocol):
    descriptor: UnsatProofCheckerDescriptor

    def check(
        self,
        *,
        certificate: Mapping[str, Any],
        variable_count: int,
        clauses: Sequence[Sequence[int]],
        subject_digest: str,
    ) -> UnsatProofCheckResult: ...


class UnsatProofCheckerRegistry:
    """Explicit repository-owned mapping from proof formats to checkers."""

    def __init__(self) -> None:
        self._by_format: dict[str, UnsatProofChecker] = {}

    def register(self, checker: UnsatProofChecker) -> None:
        proof_format = checker.descriptor.proof_format
        if proof_format in self._by_format:
            raise ValueError(f"Duplicate UNSAT proof checker for format: {proof_format}")
        self._by_format[proof_format] = checker

    def get(self, proof_format: str) -> UnsatProofChecker | None:
        return self._by_format.get(proof_format)

    def formats(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_format))


def _canonical_json_digest(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _normalize_proof_clause(raw: object, *, variable_count: int, max_width: int) -> tuple[int, ...]:
    if not isinstance(raw, (list, tuple)):
        raise ValueError("RUP proof step must be a list or tuple of integer literals")
    if len(raw) > max_width:
        raise ValueError("RUP proof clause exceeds configured width limit")
    literals: list[int] = []
    for literal in raw:
        if isinstance(literal, bool) or not isinstance(literal, int) or literal == 0:
            raise ValueError("RUP proof literals must be non-zero integers")
        if abs(literal) > variable_count:
            raise ValueError("RUP proof literal references a variable outside variable_count")
        literals.append(literal)
    # Repeated literals do not change clause semantics.  Preserve proof-step
    # order while canonicalizing each clause for deterministic checking/digest.
    return tuple(sorted(set(literals), key=lambda value: (abs(value), value)))


def _assign_literal_true(assignment: dict[int, bool], literal: int) -> bool:
    """Assign ``literal`` to true; return False when this immediately conflicts."""

    variable = abs(literal)
    value = literal > 0
    existing = assignment.get(variable)
    if existing is not None:
        return existing == value
    assignment[variable] = value
    return True


def _unit_propagation_conflicts(
    clauses: Sequence[Sequence[int]],
    *,
    assumptions_true: Sequence[int],
) -> bool:
    """Return True iff Boolean unit propagation derives contradiction.

    This is a deliberately small, deterministic checker implementation.  It is
    not a SAT solver: when propagation reaches a fixpoint without conflict it
    returns False rather than searching for a model.
    """

    assignment: dict[int, bool] = {}
    for literal in assumptions_true:
        if not _assign_literal_true(assignment, literal):
            return True

    changed = True
    while changed:
        changed = False
        for clause in clauses:
            satisfied = False
            unassigned: list[int] = []
            for literal in clause:
                value = assignment.get(abs(literal))
                if value is None:
                    unassigned.append(literal)
                    continue
                literal_true = value if literal > 0 else not value
                if literal_true:
                    satisfied = True
                    break
            if satisfied:
                continue
            if not unassigned:
                return True
            if len(unassigned) == 1:
                if not _assign_literal_true(assignment, unassigned[0]):
                    return True
                changed = True
    return False


def clause_is_rup(
    clause: Sequence[int],
    *,
    formula: Sequence[Sequence[int]],
) -> bool:
    """Check the reverse-unit-propagation property for one candidate clause."""

    # C is RUP iff F ∧ ¬C reaches conflict by unit propagation.  Negating a
    # clause means assuming the negation of every literal in that clause.
    assumptions = tuple(-literal for literal in clause)
    return _unit_propagation_conflicts(formula, assumptions_true=assumptions)


class RupUnsatProofChecker:
    """Check addition-only RUP proofs ending in the empty clause."""

    descriptor = UnsatProofCheckerDescriptor(
        checker_id=RUP_CHECKER_ID,
        version=RUP_CHECKER_VERSION,
        proof_format=RUP_PROOF_FORMAT,
    )

    def __init__(self, *, limits: ProofCheckLimits | None = None) -> None:
        self.limits = limits or ProofCheckLimits()

    def _reject(
        self,
        diagnostic: str,
        *,
        proof_digest: str | None = None,
        checked_steps: int = 0,
        total_literals: int = 0,
    ) -> UnsatProofCheckResult:
        return UnsatProofCheckResult(
            accepted=False,
            proof_format=self.descriptor.proof_format,
            checker_id=self.descriptor.checker_id,
            checker_version=self.descriptor.version,
            proof_digest=proof_digest,
            checked_steps=checked_steps,
            total_proof_literals=total_literals,
            witness=None,
            diagnostics=(diagnostic,),
        )

    def check(
        self,
        *,
        certificate: Mapping[str, Any],
        variable_count: int,
        clauses: Sequence[Sequence[int]],
        subject_digest: str,
    ) -> UnsatProofCheckResult:
        if variable_count < 1:
            return self._reject("rup_variable_count_must_be_positive")
        allowed_keys = {"kind", "proof_format", "cnf_digest", "steps"}
        unknown_keys = set(certificate) - allowed_keys
        if unknown_keys:
            return self._reject(f"rup_certificate_unknown_fields:{sorted(unknown_keys)}")
        if certificate.get("kind") != "unsat_proof":
            return self._reject("rup_certificate_kind_mismatch")
        if certificate.get("proof_format") != self.descriptor.proof_format:
            return self._reject("rup_certificate_format_mismatch")
        if certificate.get("cnf_digest") != subject_digest:
            return self._reject("rup_certificate_cnf_digest_mismatch")
        raw_steps = certificate.get("steps")
        if not isinstance(raw_steps, (list, tuple)):
            return self._reject("rup_certificate_steps_must_be_sequence")
        if not raw_steps:
            return self._reject("rup_certificate_must_contain_proof_steps")
        if len(raw_steps) > self.limits.max_steps:
            return self._reject("rup_certificate_exceeds_step_limit")

        normalized_steps: list[tuple[int, ...]] = []
        total_literals = 0
        try:
            for raw_step in raw_steps:
                step = _normalize_proof_clause(
                    raw_step,
                    variable_count=variable_count,
                    max_width=self.limits.max_clause_width,
                )
                total_literals += len(step)
                if total_literals > self.limits.max_total_literals:
                    return self._reject(
                        "rup_certificate_exceeds_literal_limit",
                        checked_steps=len(normalized_steps),
                        total_literals=total_literals,
                    )
                normalized_steps.append(step)
        except ValueError as exc:
            return self._reject(
                f"invalid_rup_certificate:{exc}",
                checked_steps=len(normalized_steps),
                total_literals=total_literals,
            )

        proof_payload = {
            "kind": "unsat_proof",
            "proof_format": self.descriptor.proof_format,
            "cnf_digest": subject_digest,
            "steps": [list(step) for step in normalized_steps],
        }
        proof_digest = _canonical_json_digest(proof_payload)
        if normalized_steps[-1] != ():
            return self._reject(
                "rup_proof_must_end_with_empty_clause",
                proof_digest=proof_digest,
                total_literals=total_literals,
            )

        working_formula: list[tuple[int, ...]] = [tuple(clause) for clause in clauses]
        for index, step in enumerate(normalized_steps, start=1):
            if not clause_is_rup(step, formula=working_formula):
                return self._reject(
                    f"rup_step_failed:{index}",
                    proof_digest=proof_digest,
                    checked_steps=index - 1,
                    total_literals=total_literals,
                )
            working_formula.append(step)

        witness = VerificationWitness.create(
            kind=WitnessKind.FORMAL_PROOF,
            subject_digest=subject_digest,
            summary="External UNSAT proof was independently checked by repository-owned RUP validation.",
            reproducible=True,
            details={
                "certificate_kind": "unsat_proof",
                "proof_format": self.descriptor.proof_format,
                "proof_digest": proof_digest,
                "checker_id": self.descriptor.checker_id,
                "checker_version": self.descriptor.version,
                "proof_steps": len(normalized_steps),
                "proof_literals": total_literals,
                "final_empty_clause": True,
                "cnf_digest": subject_digest,
                "limits": {
                    "max_steps": self.limits.max_steps,
                    "max_total_literals": self.limits.max_total_literals,
                    "max_clause_width": self.limits.max_clause_width,
                },
            },
        )
        return UnsatProofCheckResult(
            accepted=True,
            proof_format=self.descriptor.proof_format,
            checker_id=self.descriptor.checker_id,
            checker_version=self.descriptor.version,
            proof_digest=proof_digest,
            checked_steps=len(normalized_steps),
            total_proof_literals=total_literals,
            witness=witness,
            diagnostics=("rup_unsat_proof_valid",),
        )


def builtin_unsat_proof_checker_registry(
    *,
    rup_limits: ProofCheckLimits | None = None,
) -> UnsatProofCheckerRegistry:
    registry = UnsatProofCheckerRegistry()
    registry.register(RupUnsatProofChecker(limits=rup_limits))
    return registry
