#!/usr/bin/env python3
"""Rules preventing implicit inheritance of scientific scope and status."""

from __future__ import annotations

from typing import Any, Dict

NON_INHERITABLE_FIELDS = {
    "validity_scope",
    "evidence_relation_ids",
    "epistemic_state",
    "assertion_provenance",
    "temporal_status",
}

# Relationships that can justify a narrower or derived scope must be handled
# explicitly by a future semantic operation. No relationship currently grants
# automatic inheritance.
EXPLICIT_SCOPE_TRANSFER_RELATIONS = {
    # Reserved for future, explicitly justified transformations.
}


def inheritance_allowed(relationship_type: str, field: str) -> bool:
    """Return whether a relationship may implicitly transfer a scientific field."""
    normalized_type = str(relationship_type or "").strip().lower()
    normalized_field = str(field or "").strip().lower()
    if normalized_field in NON_INHERITABLE_FIELDS:
        return normalized_type in EXPLICIT_SCOPE_TRANSFER_RELATIONS
    return False


def validate_no_implicit_inheritance(relationship: Dict[str, Any]) -> list[str]:
    """Return violations for relationships carrying forbidden inherited state."""
    if not isinstance(relationship, dict):
        return ["relationship must be a mapping"]
    relation_type = relationship.get("type", "")
    errors: list[str] = []
    for field in NON_INHERITABLE_FIELDS:
        if field in relationship and relationship.get(field) not in (None, [], {}, ""):
            if not inheritance_allowed(relation_type, field):
                errors.append(
                    f"relationship type '{relation_type}' cannot implicitly carry '{field}'"
                )
    return errors
