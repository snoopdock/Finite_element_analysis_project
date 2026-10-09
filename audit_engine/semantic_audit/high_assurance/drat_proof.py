"""Repository-owned bounded DRAT proof checking for G3.4.4.

The checker implements a deliberately strict, auditable subset of text-style
DRAT as a structured JSON certificate.  Proof steps are clause additions or
clause deletions.  An added clause is accepted when it is RUP, or when it has
RAT on its first literal (the pivot).  Deletions mutate only the checker proof
state; they are not semantic evidence by themselves.

This is not a general-purpose high-performance DRAT checker.  It is a bounded
reference checker whose resource ceilings are explicit and whose failure to
finish is epistemically neutral.  External solvers remain evidence producers;
only repository-owned checking can promote a proof-carrying UNSAT result.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence

from .models import VerificationWitness, WitnessKind
from .unsat_proof import (
    UnsatProofCheckResult,
    UnsatProofCheckerDescriptor,
    clause_is_rup,
)


DRAT_PROOF_FORMAT = "cnf-drat/v1"
DRAT_CHECKER_ID = "repository-cnf-drat-checker"
DRAT_CHECKER_VERSION = "1.0.0"


@dataclass(frozen=True)
class DratProofCheckLimits:
    """Hard bounds for untrusted DRAT proof material."""

    max_steps: int = 20_000
    max_total_literals: int = 500_000
    max_clause_width: int = 5_000
    max_formula_clauses: int = 100_000
    max_rat_resolvents_per_step: int = 20_000

    def __post_init__(self) -> None:
        values = (
            self.max_steps,
            self.max_total_literals,
            self.max_clause_width,
            self.max_formula_clauses,
            self.max_rat_resolvents_per_step,
        )
        if min(values) < 1:
            raise ValueError("DRAT checker limits must be positive.")


def _canonical_json_digest(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _normalize_clause_preserve_pivot(
    raw: object,
    *,
    variable_count: int,
    max_width: int,
) -> tuple[int, ...]:
    if not isinstance(raw, (list, tuple)):
        raise ValueError("DRAT clause must be a list or tuple of integer literals")
    if len(raw) > max_width:
        raise ValueError("DRAT clause exceeds configured width limit")
    seen: set[int] = set()
    result: list[int] = []
    for literal in raw:
        if isinstance(literal, bool) or not isinstance(literal, int) or literal == 0:
            raise ValueError("DRAT literals must be non-zero integers")
        if abs(literal) > variable_count:
            raise ValueError("DRAT literal references a variable outside variable_count")
        if literal not in seen:
            seen.add(literal)
            result.append(literal)
    return tuple(result)


def _semantic_clause_key(clause: Sequence[int]) -> tuple[int, ...]:
    return tuple(sorted(set(clause), key=lambda value: (abs(value), value)))


def _is_tautology(clause: Sequence[int]) -> bool:
    literals = set(clause)
    return any(-literal in literals for literal in literals)


def _resolvent(
    candidate: Sequence[int],
    other: Sequence[int],
    *,
    pivot: int,
) -> tuple[int, ...]:
    values: list[int] = []
    seen: set[int] = set()
    for literal in candidate:
        if literal == pivot:
            continue
        if literal not in seen:
            seen.add(literal)
            values.append(literal)
    for literal in other:
        if literal == -pivot:
            continue
        if literal not in seen:
            seen.add(literal)
            values.append(literal)
    return tuple(values)


class DratUnsatProofChecker:
    """Bounded repository-owned DRAT checker with RUP and RAT additions."""

    descriptor = UnsatProofCheckerDescriptor(
        checker_id=DRAT_CHECKER_ID,
        version=DRAT_CHECKER_VERSION,
        proof_format=DRAT_PROOF_FORMAT,
    )

    def __init__(self, *, limits: DratProofCheckLimits | None = None) -> None:
        self.limits = limits or DratProofCheckLimits()

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
            return self._reject("drat_variable_count_must_be_positive")
        allowed_keys = {"kind", "proof_format", "cnf_digest", "steps"}
        unknown_keys = set(certificate) - allowed_keys
        if unknown_keys:
            return self._reject(f"drat_certificate_unknown_fields:{sorted(unknown_keys)}")
        if certificate.get("kind") != "unsat_proof":
            return self._reject("drat_certificate_kind_mismatch")
        if certificate.get("proof_format") != self.descriptor.proof_format:
            return self._reject("drat_certificate_format_mismatch")
        if certificate.get("cnf_digest") != subject_digest:
            return self._reject("drat_certificate_cnf_digest_mismatch")

        raw_steps = certificate.get("steps")
        if not isinstance(raw_steps, (list, tuple)):
            return self._reject("drat_certificate_steps_must_be_sequence")
        if not raw_steps:
            return self._reject("drat_certificate_must_contain_proof_steps")
        if len(raw_steps) > self.limits.max_steps:
            return self._reject("drat_resource_limit:step_limit")

        normalized_steps: list[dict[str, Any]] = []
        total_literals = 0
        try:
            for raw_step in raw_steps:
                if not isinstance(raw_step, Mapping):
                    raise ValueError("DRAT proof step must be an object")
                unknown = set(raw_step) - {"op", "clause"}
                if unknown:
                    raise ValueError(f"DRAT proof step has unknown fields: {sorted(unknown)}")
                op = raw_step.get("op")
                if op not in {"add", "delete"}:
                    raise ValueError("DRAT proof step op must be add or delete")
                clause = _normalize_clause_preserve_pivot(
                    raw_step.get("clause"),
                    variable_count=variable_count,
                    max_width=self.limits.max_clause_width,
                )
                total_literals += len(clause)
                if total_literals > self.limits.max_total_literals:
                    return self._reject(
                        "drat_resource_limit:literal_limit",
                        checked_steps=len(normalized_steps),
                        total_literals=total_literals,
                    )
                normalized_steps.append({"op": op, "clause": clause})
        except ValueError as exc:
            return self._reject(
                f"invalid_drat_certificate:{exc}",
                checked_steps=len(normalized_steps),
                total_literals=total_literals,
            )

        final = normalized_steps[-1]
        if final["op"] != "add" or final["clause"] != ():
            return self._reject(
                "drat_proof_must_end_with_added_empty_clause",
                total_literals=total_literals,
            )

        proof_payload = {
            "kind": "unsat_proof",
            "proof_format": self.descriptor.proof_format,
            "cnf_digest": subject_digest,
            "steps": [
                {"op": step["op"], "clause": list(step["clause"])}
                for step in normalized_steps
            ],
        }
        proof_digest = _canonical_json_digest(proof_payload)

        working_formula: list[tuple[int, ...]] = [tuple(clause) for clause in clauses]
        if len(working_formula) > self.limits.max_formula_clauses:
            return self._reject(
                "drat_resource_limit:initial_formula_clause_limit",
                proof_digest=proof_digest,
                total_literals=total_literals,
            )

        additions = deletions = rup_additions = rat_additions = rat_resolvents = 0
        for index, step in enumerate(normalized_steps, start=1):
            op = step["op"]
            clause: tuple[int, ...] = step["clause"]
            if op == "delete":
                key = _semantic_clause_key(clause)
                delete_index = next(
                    (i for i, existing in enumerate(working_formula) if _semantic_clause_key(existing) == key),
                    None,
                )
                if delete_index is None:
                    return self._reject(
                        f"drat_delete_missing_clause:{index}",
                        proof_digest=proof_digest,
                        checked_steps=index - 1,
                        total_literals=total_literals,
                    )
                working_formula.pop(delete_index)
                deletions += 1
                continue

            accepted_by_rup = clause_is_rup(clause, formula=working_formula)
            if accepted_by_rup:
                rup_additions += 1
            else:
                if not clause:
                    return self._reject(
                        f"drat_empty_clause_not_rup:{index}",
                        proof_digest=proof_digest,
                        checked_steps=index - 1,
                        total_literals=total_literals,
                    )
                pivot = clause[0]
                opposing = [existing for existing in working_formula if -pivot in existing]
                if len(opposing) > self.limits.max_rat_resolvents_per_step:
                    return self._reject(
                        f"drat_resource_limit:rat_resolvent_limit:{index}",
                        proof_digest=proof_digest,
                        checked_steps=index - 1,
                        total_literals=total_literals,
                    )
                rat_ok = True
                for other in opposing:
                    resolvent = _resolvent(clause, other, pivot=pivot)
                    rat_resolvents += 1
                    if _is_tautology(resolvent):
                        continue
                    if not clause_is_rup(resolvent, formula=working_formula):
                        rat_ok = False
                        break
                if not rat_ok:
                    return self._reject(
                        f"drat_rat_step_failed:{index}",
                        proof_digest=proof_digest,
                        checked_steps=index - 1,
                        total_literals=total_literals,
                    )
                rat_additions += 1

            working_formula.append(clause)
            additions += 1
            if len(working_formula) > self.limits.max_formula_clauses:
                return self._reject(
                    f"drat_resource_limit:formula_clause_limit:{index}",
                    proof_digest=proof_digest,
                    checked_steps=index,
                    total_literals=total_literals,
                )

        witness = VerificationWitness.create(
            kind=WitnessKind.FORMAL_PROOF,
            subject_digest=subject_digest,
            summary="External UNSAT proof was independently checked by repository-owned DRAT validation.",
            reproducible=True,
            details={
                "certificate_kind": "unsat_proof",
                "proof_format": self.descriptor.proof_format,
                "proof_digest": proof_digest,
                "checker_id": self.descriptor.checker_id,
                "checker_version": self.descriptor.version,
                "proof_steps": len(normalized_steps),
                "proof_literals": total_literals,
                "additions": additions,
                "deletions": deletions,
                "rup_additions": rup_additions,
                "rat_additions": rat_additions,
                "rat_resolvents_checked": rat_resolvents,
                "final_empty_clause": True,
                "cnf_digest": subject_digest,
                "limits": {
                    "max_steps": self.limits.max_steps,
                    "max_total_literals": self.limits.max_total_literals,
                    "max_clause_width": self.limits.max_clause_width,
                    "max_formula_clauses": self.limits.max_formula_clauses,
                    "max_rat_resolvents_per_step": self.limits.max_rat_resolvents_per_step,
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
            diagnostics=("drat_unsat_proof_valid",),
        )
