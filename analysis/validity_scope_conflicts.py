#!/usr/bin/env python3
"""Conservative comparison of validity scopes without resolving scientific disagreements."""

from __future__ import annotations

from typing import Any, Dict, List



def _norm(values: Any) -> set[str]:
    return {str(value).strip().lower() for value in values or [] if str(value).strip()}


def compare_validity_scopes(first: Dict[str, Any], second: Dict[str, Any]) -> Dict[str, Any]:
    """Classify the structural relationship between two validity scopes.

    This function does not decide scientific truth. It only identifies structural
    compatibility signals from explicitly recorded scope fields.
    """
    a = first if isinstance(first, dict) else {}
    b = second if isinstance(second, dict) else {}
    if str(a.get("proposition_id", "")).strip() != str(b.get("proposition_id", "")).strip():
        return {"status": "not_comparable", "reason": "different_propositions", "fields": []}

    differing_fields: List[str] = []
    shared_fields: List[str] = []
    conflict_signals: List[str] = []

    for field in ("framework", "domain_of_validity", "regime", "approximation"):
        av = str(a.get(field) or "").strip().lower()
        bv = str(b.get(field) or "").strip().lower()
        if av and bv:
            if av == bv:
                shared_fields.append(field)
            else:
                differing_fields.append(field)
                conflict_signals.append(f"different_{field}")

    for field in ("conditions", "assumptions"):
        av = _norm(a.get(field))
        bv = _norm(b.get(field))
        if av and bv:
            if av.issubset(bv) or bv.issubset(av):
                shared_fields.append(field)
            elif av.isdisjoint(bv):
                differing_fields.append(field)
                conflict_signals.append(f"disjoint_{field}")
            else:
                shared_fields.append(field)
                differing_fields.append(field)

    a_limits = _norm(a.get("limitations"))
    b_limits = _norm(b.get("limitations"))
    a_exceptions = _norm(a.get("exceptions"))
    b_exceptions = _norm(b.get("exceptions"))
    if a_limits & b_limits or a_exceptions & b_exceptions:
        shared_fields.append("qualifiers")

    if conflict_signals:
        if any(signal.startswith("different_framework") for signal in conflict_signals):
            status = "different_framework"
        elif any(signal.startswith("disjoint_") for signal in conflict_signals):
            status = "disjoint_conditions"
        else:
            status = "scope_difference"
    elif shared_fields:
        status = "compatible_or_overlapping"
    else:
        status = "insufficient_scope_information"

    return {
        "status": status,
        "reason": "structural_scope_comparison",
        "fields": sorted(set(shared_fields + differing_fields)),
        "shared_fields": sorted(set(shared_fields)),
        "differing_fields": sorted(set(differing_fields)),
        "conflict_signals": sorted(set(conflict_signals)),
        "scientific_resolution": "not_performed",
    }


def compare_scope_pairs(scopes: List[Dict[str, Any]], max_pairs: int = 32) -> List[Dict[str, Any]]:
    """Compare bounded same-proposition validity scopes."""
    normalized = [scope for scope in scopes or [] if isinstance(scope, dict)]
    results: List[Dict[str, Any]] = []
    limit = max(0, int(max_pairs))
    for index, first in enumerate(normalized):
        if len(results) >= limit:
            break
        for second in normalized[index + 1:]:
            if len(results) >= limit:
                break
            comparison = compare_validity_scopes(first, second)
            if comparison["status"] == "not_comparable":
                continue
            results.append({
                "validity_ids": [str(first.get("validity_id", "")), str(second.get("validity_id", ""))],
                "proposition_id": str(first.get("proposition_id", "")),
                **comparison,
            })
    return results
