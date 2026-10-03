#!/usr/bin/env python3
"""Authoritative domain semantic objects used by publication assembly.

The knowledge graph remains the authority for scientific assertions and the
semantic document remains the authority for publication placement.  This
module owns domain-object identity for mathematical equations so document
occurrences can reference a stable object without depending on graph
proposition identity or legacy writer metadata.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import re
from typing import Any, Dict, Iterable, Mapping, Optional, Set
import uuid


DOMAIN_SEMANTIC_SCHEMA_VERSION = 1


class DomainSemanticModelError(ValueError):
    """Raised when the domain semantic model violates its contract."""


def empty_domain_semantic_model() -> Dict[str, Any]:
    """Return an empty, JSON-serializable domain semantic model."""
    return {
        "schema_version": DOMAIN_SEMANTIC_SCHEMA_VERSION,
        "equation_candidates": {},
        "equations": {},
    }


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_expression_for_matching(expression: str) -> str:
    """Conservative expression normalization used only for candidate matching.

    This is deliberately not a mathematical equivalence test.  It removes
    whitespace and common outer math delimiters so duplicate discovery can be
    recognized without turning syntactic similarity into semantic identity.
    """
    text = _normalize_text(expression)
    if len(text) >= 2 and text.startswith("$") and text.endswith("$"):
        text = text[1:-1].strip()
    return re.sub(r"\s+", "", text)


def _candidate_fingerprint(name: str, expression: str) -> str:
    normalized_name = re.sub(r"\s+", " ", _normalize_text(name).casefold())
    normalized_expression = _normalize_expression_for_matching(expression)
    payload = f"{normalized_name}\n{normalized_expression}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _candidate_id(fingerprint: str) -> str:
    return f"EQC-{fingerprint[:20]}"


def _normalize_source_ids(values: Any) -> list[str]:
    if not isinstance(values, Iterable) or isinstance(values, (str, bytes, Mapping)):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        source_id = _normalize_text(value)
        if source_id and source_id not in seen:
            result.append(source_id)
            seen.add(source_id)
    return result


def normalize_domain_semantic_model(model: Any) -> Dict[str, Any]:
    """Normalize container shape while preserving stored semantic payloads."""
    if not isinstance(model, Mapping):
        return empty_domain_semantic_model()

    normalized = empty_domain_semantic_model()
    normalized["schema_version"] = model.get(
        "schema_version",
        DOMAIN_SEMANTIC_SCHEMA_VERSION,
    )
    candidates = model.get("equation_candidates", {})
    equations = model.get("equations", {})

    if isinstance(candidates, Mapping):
        normalized["equation_candidates"] = {
            str(key): deepcopy(value)
            for key, value in candidates.items()
        }
    else:
        normalized["equation_candidates"] = candidates
    if isinstance(equations, Mapping):
        normalized["equations"] = {
            str(key): deepcopy(value)
            for key, value in equations.items()
        }
    else:
        normalized["equations"] = equations

    return normalized


def validate_domain_semantic_model(model: Mapping[str, Any]) -> None:
    """Validate domain-object identity and registry consistency."""
    if not isinstance(model, Mapping):
        raise DomainSemanticModelError("domain_semantic_model must be a mapping.")
    if int(model.get("schema_version", -1)) != DOMAIN_SEMANTIC_SCHEMA_VERSION:
        raise DomainSemanticModelError("Unsupported domain semantic schema version.")

    candidates = model.get("equation_candidates")
    equations = model.get("equations")
    if not isinstance(candidates, Mapping) or not isinstance(equations, Mapping):
        raise DomainSemanticModelError(
            "domain_semantic_model requires equation_candidates and equations mappings."
        )

    equation_ids: set[str] = set()
    for key, equation in equations.items():
        if not isinstance(equation, Mapping):
            raise DomainSemanticModelError(f"Equation {key!r} must be a mapping.")
        equation_id = _normalize_text(equation.get("equation_id"))
        expression = _normalize_text(equation.get("expression"))
        status = _normalize_text(equation.get("status"))
        if not equation_id or equation_id != str(key):
            raise DomainSemanticModelError(f"Equation key/id mismatch for {key!r}.")
        if equation_id in equation_ids:
            raise DomainSemanticModelError(f"Duplicate equation_id: {equation_id}.")
        if not expression:
            raise DomainSemanticModelError(
                f"Equation {equation_id!r} requires a non-empty expression."
            )
        if status != "accepted":
            raise DomainSemanticModelError(
                f"Authoritative equation {equation_id!r} must have status 'accepted'."
            )
        source_ids = equation.get("source_ids", [])
        if not isinstance(source_ids, list) or any(
            not isinstance(source_id, str) or not source_id.strip()
            for source_id in source_ids
        ):
            raise DomainSemanticModelError(
                f"Equation {equation_id!r} source_ids must be non-empty strings."
            )
        equation_ids.add(equation_id)

    for key, candidate in candidates.items():
        if not isinstance(candidate, Mapping):
            raise DomainSemanticModelError(f"Equation candidate {key!r} must be a mapping.")
        candidate_id = _normalize_text(candidate.get("candidate_id"))
        expression = _normalize_text(candidate.get("expression"))
        status = _normalize_text(candidate.get("status"))
        if not candidate_id or candidate_id != str(key):
            raise DomainSemanticModelError(
                f"Equation candidate key/id mismatch for {key!r}."
            )
        if not expression:
            raise DomainSemanticModelError(
                f"Equation candidate {candidate_id!r} requires an expression."
            )
        if status not in {"candidate", "promoted"}:
            raise DomainSemanticModelError(
                f"Equation candidate {candidate_id!r} has invalid status {status!r}."
            )
        promoted_id = candidate.get("equation_id")
        if status == "promoted":
            if not isinstance(promoted_id, str) or promoted_id not in equations:
                raise DomainSemanticModelError(
                    f"Promoted candidate {candidate_id!r} must reference an existing equation."
                )
        elif promoted_id is not None:
            raise DomainSemanticModelError(
                f"Unpromoted candidate {candidate_id!r} may not define equation_id."
            )


def ingest_equation_candidates(
    model: Mapping[str, Any],
    extracted_equations: Any,
    valid_source_ids: Set[str],
) -> Dict[str, Any]:
    """Ingest source-supported equation candidates without granting authority.

    Exact normalized name+expression matching is used only to consolidate
    repeated discovery of the same candidate.  It is not mathematical
    equivalence and never creates an authoritative equation automatically.
    """
    result = normalize_domain_semantic_model(model)
    candidates = result["equation_candidates"]
    valid_sources = {str(value) for value in (valid_source_ids or set()) if value}

    if not isinstance(extracted_equations, list):
        validate_domain_semantic_model(result)
        return result

    for raw in extracted_equations:
        if not isinstance(raw, Mapping):
            continue
        name = _normalize_text(raw.get("name"))
        expression = _normalize_text(raw.get("latex") or raw.get("expression"))
        meaning = _normalize_text(raw.get("explanation") or raw.get("meaning"))
        if not name or not expression:
            continue

        source_ids = [
            source_id
            for source_id in _normalize_source_ids(raw.get("source_ids", []))
            if source_id in valid_sources
        ]
        if not source_ids:
            continue

        fingerprint = _candidate_fingerprint(name, expression)
        candidate_id = _candidate_id(fingerprint)
        existing = candidates.get(candidate_id)

        if existing is None:
            candidates[candidate_id] = {
                "candidate_id": candidate_id,
                "fingerprint": fingerprint,
                "name": name,
                "expression": expression,
                "meaning": meaning,
                "source_ids": source_ids,
                "status": "candidate",
            }
            continue

        # Repeated discovery may add evidence, but it does not alter the
        # candidate's scientific payload or authority status.
        merged_sources = list(existing.get("source_ids", []))
        for source_id in source_ids:
            if source_id not in merged_sources:
                merged_sources.append(source_id)
        existing["source_ids"] = merged_sources

    validate_domain_semantic_model(result)
    return result


def promote_equation_candidate(
    model: Mapping[str, Any],
    candidate_id: str,
    *,
    proposition_ids: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Explicitly promote one candidate into the authoritative equation registry."""
    result = normalize_domain_semantic_model(model)
    candidates = result["equation_candidates"]
    equations = result["equations"]

    candidate = candidates.get(candidate_id)
    if not isinstance(candidate, dict):
        raise DomainSemanticModelError(f"Unknown equation candidate: {candidate_id}.")

    if candidate.get("status") == "promoted":
        equation_id = candidate.get("equation_id")
        if isinstance(equation_id, str) and equation_id in equations:
            validate_domain_semantic_model(result)
            return result
        raise DomainSemanticModelError(
            f"Candidate {candidate_id!r} is marked promoted without a valid equation."
        )

    equation_id = f"EQ-{uuid.uuid4()}"
    linked_propositions = _normalize_source_ids(list(proposition_ids or []))
    equations[equation_id] = {
        "equation_id": equation_id,
        "expression": str(candidate["expression"]),
        "meaning": str(candidate.get("meaning", "")),
        "source_ids": list(candidate.get("source_ids", [])),
        "status": "accepted",
        "provenance": {
            "candidate_id": candidate_id,
        },
        "proposition_ids": linked_propositions,
    }
    candidate["status"] = "promoted"
    candidate["equation_id"] = equation_id

    validate_domain_semantic_model(result)
    return result


def get_authorized_equation_ids(model: Mapping[str, Any]) -> Set[str]:
    normalized = normalize_domain_semantic_model(model)
    validate_domain_semantic_model(normalized)
    return set(normalized["equations"])


def resolve_equation(model: Mapping[str, Any], equation_id: str) -> Dict[str, Any]:
    normalized = normalize_domain_semantic_model(model)
    validate_domain_semantic_model(normalized)
    equation = normalized["equations"].get(equation_id)
    if not isinstance(equation, Mapping):
        raise DomainSemanticModelError(f"Unknown equation_id: {equation_id}.")
    return deepcopy(dict(equation))
