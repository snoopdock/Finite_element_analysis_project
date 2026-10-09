"""Streaming repository-owned checking of detached CNF proof artifacts.

G3.4.5 introduces a JSON-lines proof artifact format so large RUP/DRAT proofs do
not have to be embedded in one solver response or materialized as one Python
object.  The artifact itself is content-addressed and verified by
:mod:`proof_artifact`; this module then parses and checks it line by line.

The active CNF/proof formula must still be retained for RUP/RAT semantics, but
proof *steps* are not accumulated.  Resource exhaustion or artifact retrieval
failure is epistemically neutral and never establishes SAT or UNSAT.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, BinaryIO, Mapping, Sequence

from .drat_proof import DRAT_CHECKER_ID, DRAT_CHECKER_VERSION, DRAT_PROOF_FORMAT
from .models import VerificationWitness, WitnessKind
from .proof_artifact import (
    DETACHED_UNSAT_PROOF_KIND,
    PROOF_ARTIFACT_FORMAT,
    ProofArtifactError,
    ProofArtifactReference,
    ProofArtifactStoreRegistry,
)
from .unsat_proof import (
    RUP_CHECKER_ID,
    RUP_CHECKER_VERSION,
    RUP_PROOF_FORMAT,
    UnsatProofCheckResult,
    clause_is_rup,
)


STREAMING_PROOF_CHECKER_VERSION = "1.0.0"


@dataclass(frozen=True)
class StreamingProofCheckLimits:
    max_artifact_bytes: int = 256 * 1024 * 1024
    max_line_bytes: int = 2 * 1024 * 1024
    max_steps: int = 2_000_000
    max_total_literals: int = 25_000_000
    max_clause_width: int = 100_000
    max_formula_clauses: int = 4_000_000
    max_rat_resolvents_per_step: int = 250_000

    def __post_init__(self) -> None:
        values = (
            self.max_artifact_bytes,
            self.max_line_bytes,
            self.max_steps,
            self.max_total_literals,
            self.max_clause_width,
            self.max_formula_clauses,
            self.max_rat_resolvents_per_step,
        )
        if min(values) < 1:
            raise ValueError("Streaming proof limits must be positive")


def _normalize_clause(
    raw: object,
    *,
    variable_count: int,
    max_width: int,
    preserve_order: bool,
) -> tuple[int, ...]:
    if not isinstance(raw, (list, tuple)):
        raise ValueError("proof clause must be a list or tuple")
    if len(raw) > max_width:
        raise ValueError("proof clause exceeds configured width limit")
    values: list[int] = []
    seen: set[int] = set()
    for literal in raw:
        if isinstance(literal, bool) or not isinstance(literal, int) or literal == 0:
            raise ValueError("proof literals must be non-zero integers")
        if abs(literal) > variable_count:
            raise ValueError("proof literal references variable outside variable_count")
        if literal not in seen:
            seen.add(literal)
            values.append(literal)
    if preserve_order:
        return tuple(values)
    return tuple(sorted(values, key=lambda value: (abs(value), value)))


def _semantic_clause_key(clause: Sequence[int]) -> tuple[int, ...]:
    return tuple(sorted(set(clause), key=lambda value: (abs(value), value)))


def _is_tautology(clause: Sequence[int]) -> bool:
    values = set(clause)
    return any(-literal in values for literal in values)


def _resolvent(left: Sequence[int], right: Sequence[int], *, pivot: int) -> tuple[int, ...]:
    values: list[int] = []
    seen: set[int] = set()
    for literal in left:
        if literal == pivot:
            continue
        if literal not in seen:
            seen.add(literal)
            values.append(literal)
    for literal in right:
        if literal == -pivot:
            continue
        if literal not in seen:
            seen.add(literal)
            values.append(literal)
    return tuple(values)


def _read_json_line(handle: BinaryIO, *, max_line_bytes: int, line_number: int) -> Mapping[str, Any] | None:
    raw = handle.readline(max_line_bytes + 1)
    if raw == b"":
        return None
    if len(raw) > max_line_bytes:
        raise ValueError(f"proof artifact line exceeds byte limit:{line_number}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"proof artifact line is not UTF-8:{line_number}") from exc
    if not text.strip():
        raise ValueError(f"proof artifact contains blank line:{line_number}")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"proof artifact line is not valid JSON:{line_number}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"proof artifact line must be a JSON object:{line_number}")
    return payload


class StreamingDetachedProofChecker:
    """Check one detached RUP/DRAT proof from a registered content store."""

    def __init__(
        self,
        stores: ProofArtifactStoreRegistry,
        *,
        limits: StreamingProofCheckLimits | None = None,
    ) -> None:
        self.stores = stores
        self.limits = limits or StreamingProofCheckLimits()

    def _reject(
        self,
        reference: ProofArtifactReference,
        diagnostic: str,
        *,
        checked_steps: int = 0,
        total_literals: int = 0,
    ) -> UnsatProofCheckResult:
        checker_id, checker_version = self._checker_identity(reference.proof_format)
        return UnsatProofCheckResult(
            accepted=False,
            proof_format=reference.proof_format,
            checker_id=checker_id,
            checker_version=checker_version,
            proof_digest=reference.artifact_sha256,
            checked_steps=checked_steps,
            total_proof_literals=total_literals,
            witness=None,
            diagnostics=(diagnostic,),
        )

    @staticmethod
    def _checker_identity(proof_format: str) -> tuple[str, str]:
        if proof_format == RUP_PROOF_FORMAT:
            return f"{RUP_CHECKER_ID}-streaming", STREAMING_PROOF_CHECKER_VERSION
        if proof_format == DRAT_PROOF_FORMAT:
            return f"{DRAT_CHECKER_ID}-streaming", STREAMING_PROOF_CHECKER_VERSION
        return "repository-detached-proof-checker", STREAMING_PROOF_CHECKER_VERSION

    def check(
        self,
        *,
        reference: ProofArtifactReference,
        variable_count: int,
        clauses: Sequence[Sequence[int]],
        subject_digest: str,
    ) -> UnsatProofCheckResult:
        if variable_count < 1:
            return self._reject(reference, "detached_proof_variable_count_must_be_positive")
        if reference.cnf_digest != subject_digest:
            return self._reject(reference, "detached_proof_cnf_digest_mismatch")
        if reference.proof_format not in {RUP_PROOF_FORMAT, DRAT_PROOF_FORMAT}:
            return self._reject(reference, f"unsupported_detached_proof_format:{reference.proof_format}")
        store = self.stores.get(reference.store_id)
        if store is None:
            return self._reject(reference, f"unregistered_proof_artifact_store:{reference.store_id}")

        try:
            with store.open_verified(reference, max_bytes=self.limits.max_artifact_bytes) as handle:
                return self._check_verified_stream(
                    handle,
                    reference=reference,
                    variable_count=variable_count,
                    clauses=clauses,
                    subject_digest=subject_digest,
                )
        except (ProofArtifactError, OSError) as exc:
            return self._reject(reference, f"detached_proof_artifact_error:{exc}")

    def _check_verified_stream(
        self,
        handle: BinaryIO,
        *,
        reference: ProofArtifactReference,
        variable_count: int,
        clauses: Sequence[Sequence[int]],
        subject_digest: str,
    ) -> UnsatProofCheckResult:
        try:
            header = _read_json_line(handle, max_line_bytes=self.limits.max_line_bytes, line_number=1)
        except ValueError as exc:
            return self._reject(reference, f"invalid_detached_proof_header:{exc}")
        if header is None:
            return self._reject(reference, "detached_proof_artifact_is_empty")
        allowed_header = {"artifact_format", "proof_format", "cnf_digest"}
        unknown = set(header) - allowed_header
        if unknown:
            return self._reject(reference, f"detached_proof_header_unknown_fields:{sorted(unknown)}")
        if set(header) != allowed_header:
            return self._reject(reference, "detached_proof_header_missing_fields")
        if header["artifact_format"] != PROOF_ARTIFACT_FORMAT:
            return self._reject(reference, "detached_proof_artifact_format_mismatch")
        if header["proof_format"] != reference.proof_format:
            return self._reject(reference, "detached_proof_format_reference_mismatch")
        if header["cnf_digest"] != subject_digest:
            return self._reject(reference, "detached_proof_header_cnf_digest_mismatch")

        working_formula: list[tuple[int, ...]] = [tuple(clause) for clause in clauses]
        if len(working_formula) > self.limits.max_formula_clauses:
            return self._reject(reference, "detached_proof_resource_limit:initial_formula_clause_limit")

        steps = total_literals = additions = deletions = rup_additions = rat_additions = rat_resolvents = 0
        final_was_added_empty = False
        while True:
            line_number = steps + 2
            try:
                payload = _read_json_line(
                    handle,
                    max_line_bytes=self.limits.max_line_bytes,
                    line_number=line_number,
                )
            except ValueError as exc:
                return self._reject(
                    reference,
                    f"invalid_detached_proof_step:{exc}",
                    checked_steps=steps,
                    total_literals=total_literals,
                )
            if payload is None:
                break
            steps += 1
            if steps > self.limits.max_steps:
                return self._reject(
                    reference,
                    "detached_proof_resource_limit:step_limit",
                    checked_steps=steps - 1,
                    total_literals=total_literals,
                )
            unknown_step = set(payload) - {"op", "clause"}
            if unknown_step:
                return self._reject(
                    reference,
                    f"detached_proof_step_unknown_fields:{sorted(unknown_step)}",
                    checked_steps=steps - 1,
                    total_literals=total_literals,
                )
            if set(payload) != {"op", "clause"}:
                return self._reject(
                    reference,
                    "detached_proof_step_missing_fields",
                    checked_steps=steps - 1,
                    total_literals=total_literals,
                )
            op = payload["op"]
            if reference.proof_format == RUP_PROOF_FORMAT and op != "add":
                return self._reject(
                    reference,
                    "detached_rup_step_op_must_be_add",
                    checked_steps=steps - 1,
                    total_literals=total_literals,
                )
            if reference.proof_format == DRAT_PROOF_FORMAT and op not in {"add", "delete"}:
                return self._reject(
                    reference,
                    "detached_drat_step_op_must_be_add_or_delete",
                    checked_steps=steps - 1,
                    total_literals=total_literals,
                )
            try:
                clause = _normalize_clause(
                    payload["clause"],
                    variable_count=variable_count,
                    max_width=self.limits.max_clause_width,
                    preserve_order=reference.proof_format == DRAT_PROOF_FORMAT,
                )
            except ValueError as exc:
                return self._reject(
                    reference,
                    f"invalid_detached_proof_clause:{exc}",
                    checked_steps=steps - 1,
                    total_literals=total_literals,
                )
            total_literals += len(clause)
            if total_literals > self.limits.max_total_literals:
                return self._reject(
                    reference,
                    "detached_proof_resource_limit:literal_limit",
                    checked_steps=steps - 1,
                    total_literals=total_literals,
                )

            final_was_added_empty = op == "add" and clause == ()
            if op == "delete":
                key = _semantic_clause_key(clause)
                delete_index = next(
                    (index for index, existing in enumerate(working_formula) if _semantic_clause_key(existing) == key),
                    None,
                )
                if delete_index is None:
                    return self._reject(
                        reference,
                        f"detached_drat_delete_missing_clause:{steps}",
                        checked_steps=steps - 1,
                        total_literals=total_literals,
                    )
                working_formula.pop(delete_index)
                deletions += 1
                continue

            if clause_is_rup(clause, formula=working_formula):
                rup_additions += 1
            elif reference.proof_format == RUP_PROOF_FORMAT:
                return self._reject(
                    reference,
                    f"detached_rup_step_failed:{steps}",
                    checked_steps=steps - 1,
                    total_literals=total_literals,
                )
            else:
                if not clause:
                    return self._reject(
                        reference,
                        f"detached_drat_empty_clause_not_rup:{steps}",
                        checked_steps=steps - 1,
                        total_literals=total_literals,
                    )
                pivot = clause[0]
                opposing = [existing for existing in working_formula if -pivot in existing]
                if len(opposing) > self.limits.max_rat_resolvents_per_step:
                    return self._reject(
                        reference,
                        f"detached_proof_resource_limit:rat_resolvent_limit:{steps}",
                        checked_steps=steps - 1,
                        total_literals=total_literals,
                    )
                for other in opposing:
                    resolvent = _resolvent(clause, other, pivot=pivot)
                    rat_resolvents += 1
                    if _is_tautology(resolvent):
                        continue
                    if not clause_is_rup(resolvent, formula=working_formula):
                        return self._reject(
                            reference,
                            f"detached_drat_rat_step_failed:{steps}",
                            checked_steps=steps - 1,
                            total_literals=total_literals,
                        )
                rat_additions += 1

            working_formula.append(clause)
            additions += 1
            if len(working_formula) > self.limits.max_formula_clauses:
                return self._reject(
                    reference,
                    f"detached_proof_resource_limit:formula_clause_limit:{steps}",
                    checked_steps=steps,
                    total_literals=total_literals,
                )

        if steps == 0:
            return self._reject(reference, "detached_proof_must_contain_steps")
        if not final_was_added_empty:
            return self._reject(
                reference,
                "detached_proof_must_end_with_added_empty_clause",
                checked_steps=steps,
                total_literals=total_literals,
            )

        checker_id, checker_version = self._checker_identity(reference.proof_format)
        witness = VerificationWitness.create(
            kind=WitnessKind.FORMAL_PROOF,
            subject_digest=subject_digest,
            summary="Detached UNSAT proof artifact was content-verified and checked incrementally by repository code.",
            reproducible=True,
            details={
                "certificate_kind": DETACHED_UNSAT_PROOF_KIND,
                "artifact_sha256": reference.artifact_sha256,
                "artifact_byte_size": reference.byte_size,
                "artifact_store_id": reference.store_id,
                "artifact_format": reference.artifact_format,
                "proof_format": reference.proof_format,
                "checker_id": checker_id,
                "checker_version": checker_version,
                "proof_steps": steps,
                "proof_literals": total_literals,
                "additions": additions,
                "deletions": deletions,
                "rup_additions": rup_additions,
                "rat_additions": rat_additions,
                "rat_resolvents_checked": rat_resolvents,
                "final_empty_clause": True,
                "cnf_digest": subject_digest,
                "streaming": True,
                "proof_steps_materialized": False,
            },
        )
        return UnsatProofCheckResult(
            accepted=True,
            proof_format=reference.proof_format,
            checker_id=checker_id,
            checker_version=checker_version,
            proof_digest=reference.artifact_sha256,
            checked_steps=steps,
            total_proof_literals=total_literals,
            witness=witness,
            diagnostics=("detached_unsat_proof_valid",),
        )
