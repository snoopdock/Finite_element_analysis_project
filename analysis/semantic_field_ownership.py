#!/usr/bin/env python3
"""Semantic ownership rules for overlapping scientific fields."""

from __future__ import annotations

from typing import Dict

FIELD_OWNERSHIP: Dict[str, Dict[str, str]] = {
    "conditions": {
        "evidence": "reported_by_source",
        "assertion": "asserted_in_source_context",
        "proposition": "part_of_proposition_formulation",
        "validity_scope": "governs_claim_applicability",
    },
    "assumptions": {
        "evidence": "reported_by_source",
        "assertion": "asserted_in_source_context",
        "proposition": "part_of_proposition_formulation",
        "validity_scope": "governs_claim_applicability",
    },
    "framework": {
        "evidence": "reported_by_source",
        "assertion": "source_framework",
        "proposition": "proposition_framework",
        "validity_scope": "validity_framework",
    },
    "domain_of_validity": {
        "proposition": "stated_or_normalized_scope",
        "validity_scope": "explicit_applicability_domain",
    },
    "limitations": {
        "evidence": "reported_by_source",
        "proposition": "known_proposition_limits",
        "validity_scope": "scope_limits_or_exceptions",
        "epistemic_state": "assessment_limitations",
    },
}


def field_role(layer: str, field: str) -> str | None:
    """Return the semantic role of a field within a layer."""
    return FIELD_OWNERSHIP.get(field, {}).get(layer)


def can_overwrite(target_layer: str, field: str, source_layer: str) -> bool:
    """Only allow overwrite when both layers explicitly share a semantic role."""
    target_role = field_role(target_layer, field)
    source_role = field_role(source_layer, field)
    return bool(target_role and source_role and target_role == source_role)
