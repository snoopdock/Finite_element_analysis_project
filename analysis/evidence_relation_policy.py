#!/usr/bin/env python3
"""Policy helpers for evidence-to-proposition assessment and retention."""

from __future__ import annotations

from typing import Any, Dict

_RELATION_TO_STATE = {
    "supports": "supporting",
    "challenges": "challenging",
    "qualifies": "qualifying",
    "provides_context_for": "contextual",
    "reproduces": "reproducing",
    "does_not_address": "non_evidence",
    "unknown": "unresolved",
}


def evidence_relation_state(relation: Dict[str, Any]) -> str:
    """Map an assessed evidence relation to a neutral retention state."""
    if not isinstance(relation, dict):
        return "unresolved"
    return _RELATION_TO_STATE.get(
        str(relation.get("relationship", "unknown")).strip().lower(),
        "unresolved",
    )


def is_verification_assertion(relation: Dict[str, Any]) -> bool:
    """Return True only for explicit verification fields; evidence relation types do not imply them."""
    return isinstance(relation, dict) and bool(relation.get("verified"))


def validate_evidence_relation_for_retention(relation: Dict[str, Any]) -> Dict[str, Any]:
    """Return retention diagnostics without converting evidence into scientific truth."""
    state = evidence_relation_state(relation)
    issues = []
    if not isinstance(relation, dict):
        return {"valid": False, "state": "unresolved", "issues": ["relation is not an object"]}
    if not str(relation.get("source_id", "")).strip():
        issues.append("missing source_id")
    if not str(relation.get("proposition_id", "")).strip():
        issues.append("missing proposition_id")
    if "verified" in relation and relation.get("relationship") in _RELATION_TO_STATE:
        issues.append("evidence relation must not carry verification semantics")
    return {
        "valid": not issues,
        "state": state,
        "issues": issues,
        "is_verification_assertion": is_verification_assertion(relation),
    }
