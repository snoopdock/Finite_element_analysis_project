#!/usr/bin/env python3
"""Conservative scope-aware contradiction classification."""

from __future__ import annotations

from typing import Any, Dict, List

CONTRADICTION_CLASSES = {
    "no_conflict",
    "scope_mismatch",
    "potential_conflict",
    "conflict_under_same_scope",
    "insufficient_information",
}


def _norm(value: Any) -> set[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return set()
    return {str(item).strip().lower() for item in value if str(item).strip()}


def classify_scope_relationship(left: Dict[str, Any], right: Dict[str, Any]) -> str:
    """Classify whether two validity scopes actually overlap enough for conflict analysis."""
    if not isinstance(left, dict) or not isinstance(right, dict):
        return "insufficient_information"

    left_framework = str(left.get("framework") or "").strip().lower()
    right_framework = str(right.get("framework") or "").strip().lower()
    if left_framework and right_framework and left_framework != right_framework:
        return "scope_mismatch"

    left_conditions = _norm(left.get("conditions", [])) | _norm(left.get("assumptions", []))
    right_conditions = _norm(right.get("conditions", [])) | _norm(right.get("assumptions", []))
    if left_conditions and right_conditions and left_conditions.isdisjoint(right_conditions):
        return "scope_mismatch"
    if not left_conditions or not right_conditions:
        return "insufficient_information"
    return "potential_conflict"


def classify_proposition_pair(
    left_proposition: Dict[str, Any],
    right_proposition: Dict[str, Any],
) -> Dict[str, Any]:
    """Classify an apparent contradiction without resolving scientific truth."""
    left_scope = left_proposition.get("validity_scope", {})
    right_scope = right_proposition.get("validity_scope", {})
    scope_class = classify_scope_relationship(left_scope, right_scope)

    left_statement = str(left_proposition.get("statement") or "").strip().lower()
    right_statement = str(right_proposition.get("statement") or "").strip().lower()
    if not left_statement or not right_statement:
        result = "insufficient_information"
    elif scope_class == "scope_mismatch":
        result = "scope_mismatch"
    elif left_statement == right_statement:
        result = "no_conflict"
    elif scope_class in {"potential_conflict", "conflict_under_same_scope"}:
        result = scope_class
    else:
        result = "insufficient_information"

    return {
        "classification": result,
        "scientific_truth_resolved": False,
        "reason": "Scope comparison classifies apparent compatibility only; it does not determine which proposition is correct.",
    }
