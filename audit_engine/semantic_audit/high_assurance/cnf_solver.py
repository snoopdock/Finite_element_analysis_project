"""Deterministic bounded CNF satisfiability verifier for G3.4.1.

This adapter is intentionally small and explicit.  It is a real exhaustive
solver for bounded Boolean CNF instances, not a facade over the inactive
``formal/`` placeholders.  Its purpose is to exercise the solver verification
contract end-to-end while retaining a reproducible validation envelope.
"""

from __future__ import annotations

from itertools import product
import hashlib
import json
from typing import Iterable, Sequence

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.verification.models import VerificationContext, VerificationDecision

from .adapter import HighAssuranceAdapterDescriptor
from .models import (
    AssuranceMechanism,
    ContainmentMode,
    HighAssuranceRequest,
    HighAssuranceResult,
    ValidationCompleteness,
    ValidationEnvelope,
    VerificationWitness,
    WitnessKind,
)


BOUNDED_CNF_SAT_OBLIGATION = "bounded_cnf_satisfiability"
BOUNDED_CNF_ADAPTER_ID = "bounded-cnf-exhaustive"
BOUNDED_CNF_ADAPTER_VERSION = "1.0.0"
MAX_BOUNDED_CNF_VARIABLES = 12


def _normalize_cnf(raw_clauses: object, variable_count: int) -> tuple[tuple[int, ...], ...]:
    if not isinstance(raw_clauses, (list, tuple)):
        raise ValueError("clauses must be a list or tuple of clauses.")
    normalized: list[tuple[int, ...]] = []
    for clause in raw_clauses:
        if not isinstance(clause, (list, tuple)):
            raise ValueError("each CNF clause must be a list or tuple of integer literals.")
        literals: list[int] = []
        for literal in clause:
            if isinstance(literal, bool) or not isinstance(literal, int) or literal == 0:
                raise ValueError("CNF literals must be non-zero integers.")
            if abs(literal) > variable_count:
                raise ValueError("CNF literal references a variable outside variable_count.")
            literals.append(literal)
        # Literal duplication is semantically redundant. Canonicalization keeps
        # identity deterministic without changing satisfiability.
        normalized.append(tuple(sorted(set(literals), key=lambda value: (abs(value), value))))
    return tuple(sorted(normalized))


def _cnf_digest(variable_count: int, clauses: Sequence[Sequence[int]]) -> str:
    payload = {"variable_count": variable_count, "clauses": [list(c) for c in clauses]}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _clause_true(clause: Sequence[int], assignment: Sequence[bool]) -> bool:
    for literal in clause:
        value = assignment[abs(literal) - 1]
        if literal < 0:
            value = not value
        if value:
            return True
    return False


def _cnf_true(clauses: Sequence[Sequence[int]], assignment: Sequence[bool]) -> bool:
    return all(_clause_true(clause, assignment) for clause in clauses)


class BoundedCnfSolverAdapter:
    """Exhaustively solve CNF instances up to ``max_variables`` variables.

    Exhaustiveness is structural rather than timing-dependent: a request that
    exceeds the declared bound is rejected before solving.  For accepted
    instances every Boolean assignment is either enumerated until a model is
    found, or all assignments are exhausted to establish UNSAT within scope.
    """

    descriptor = HighAssuranceAdapterDescriptor(
        adapter_id=BOUNDED_CNF_ADAPTER_ID,
        version=BOUNDED_CNF_ADAPTER_VERSION,
        supported_obligation_types=(BOUNDED_CNF_SAT_OBLIGATION,),
        mechanism=AssuranceMechanism.SOLVER,
        containment_mode=ContainmentMode.IN_PROCESS_READ_ONLY,
        maximum_evidence_state=VerificationStatus.VALIDATED,
        deterministic=True,
        side_effect_free=True,
        requires_network=False,
        produces_witness=True,
    )

    def __init__(self, *, max_variables: int = MAX_BOUNDED_CNF_VARIABLES) -> None:
        if max_variables < 1 or max_variables > MAX_BOUNDED_CNF_VARIABLES:
            raise ValueError(
                f"max_variables must be between 1 and {MAX_BOUNDED_CNF_VARIABLES}."
            )
        self.max_variables = max_variables

    def execute(
        self,
        request: HighAssuranceRequest,
        context: VerificationContext,
    ) -> HighAssuranceResult:
        raw_count = request.parameters.get("variable_count")
        if isinstance(raw_count, bool) or not isinstance(raw_count, int):
            raise ValueError("variable_count must be an integer.")
        if raw_count < 1 or raw_count > self.max_variables:
            raise ValueError(
                f"variable_count must be between 1 and configured max_variables={self.max_variables}."
            )
        expected = request.parameters.get("expected_satisfiable")
        if not isinstance(expected, bool):
            raise ValueError("expected_satisfiable must be boolean.")

        clauses = _normalize_cnf(request.parameters.get("clauses"), raw_count)
        digest = _cnf_digest(raw_count, clauses)
        checked = 0
        model: tuple[bool, ...] | None = None
        for assignment in product((False, True), repeat=raw_count):
            checked += 1
            if _cnf_true(clauses, assignment):
                model = tuple(assignment)
                break

        satisfiable = model is not None
        decision = (
            VerificationDecision.CONFIRMED
            if satisfiable == expected
            else VerificationDecision.REFUTED
        )
        total_assignments = 2 ** raw_count
        envelope = ValidationEnvelope.create(
            subject_digest=digest,
            tool_id="bounded-cnf-exhaustive",
            tool_version=BOUNDED_CNF_ADAPTER_VERSION,
            checked_scope=(
                "propositional_boolean_cnf",
                f"variables:1..{raw_count}",
                "truth_assignment_enumeration",
            ),
            assumptions=(
                "clauses and variable_count completely encode the intended Boolean CNF instance",
                "integer literal n denotes variable n and -n denotes its negation",
            ),
            excluded_scope=(
                "first-order logic",
                "SMT theories",
                "optimization objectives",
                "external SAT solver implementations",
                f"CNF instances above {self.max_variables} variables",
            ),
            completeness=ValidationCompleteness.EXHAUSTIVE_WITHIN_SCOPE,
            environment={
                "solver_contract": "bounded_cnf_exhaustive/v1",
                "max_variables": self.max_variables,
                "total_assignment_space": total_assignments,
            },
        )

        if satisfiable:
            assert model is not None
            assignment = {str(index + 1): value for index, value in enumerate(model)}
            witness = VerificationWitness.create(
                kind=WitnessKind.SOLVER_CERTIFICATE,
                subject_digest=digest,
                summary="A satisfying Boolean assignment was found by deterministic enumeration.",
                reproducible=True,
                details={
                    "verdict": "sat",
                    "assignment": assignment,
                    "checked_assignments": checked,
                    "cnf_digest": digest,
                },
            )
        else:
            witness = VerificationWitness.create(
                kind=WitnessKind.SOLVER_CERTIFICATE,
                subject_digest=digest,
                summary="All Boolean assignments were exhausted without finding a model.",
                reproducible=True,
                details={
                    "verdict": "unsat",
                    "checked_assignments": checked,
                    "total_assignments": total_assignments,
                    "cnf_digest": digest,
                    "certificate_method": "complete_truth_table_exhaustion",
                },
            )

        return HighAssuranceResult.create(
            request=request,
            adapter_version=self.descriptor.version,
            decision=decision,
            evidence_state=VerificationStatus.VALIDATED,
            validation_envelope=envelope,
            witnesses=(witness,),
            diagnostics=(f"solver_verdict={'sat' if satisfiable else 'unsat'}",),
        )
