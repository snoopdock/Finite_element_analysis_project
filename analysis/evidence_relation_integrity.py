#!/usr/bin/env python3
"""Deterministic integrity checks for evidence-to-proposition relations."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

_ALLOWED_RELATIONS = {
    "supports",
    "challenges",
    "qualifies",
    "provides_context_for",
    "reproduces",
    "does_not_address",
    "unknown",
}


def _clean_ids(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values or []:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def validate_evidence_relation(
    relation: Dict[str, Any],
    *,
    source_ids: Iterable[Any] = (),
    proposition_ids: Iterable[Any] = (),
    location_ids: Iterable[Any] = (),
) -> List[str]:
    """Return deterministic validation errors; do not modify the relation."""
    errors: List[str] = []
    if not isinstance(relation, dict):
        return ["relation must be an object"]

    relation_id = str(relation.get("evidence_relation_id", "")).strip()
    source_id = str(relation.get("source_id", "")).strip()
    proposition_id = str(relation.get("proposition_id", "")).strip()
    relationship = str(relation.get("relationship", "")).strip().lower()

    if not relation_id:
        errors.append("missing evidence_relation_id")
    if not source_id:
        errors.append("missing source_id")
    elif source_id not in set(_clean_ids(source_ids)):
        errors.append("unknown source_id")
    if not proposition_id:
        errors.append("missing proposition_id")
    elif proposition_id not in set(_clean_ids(proposition_ids)):
        errors.append("unknown proposition_id")
    if relationship not in _ALLOWED_RELATIONS:
        errors.append("invalid relationship")

    for passage_id in _clean_ids(relation.get("passage_ids", [])):
        if passage_id not in set(_clean_ids(location_ids)):
            errors.append(f"unknown passage_id: {passage_id}")

    if "verified" in relation:
        errors.append("evidence relation must not carry verification state")
    if "verification_status" in relation:
        errors.append("evidence relation must not carry verification state")

    try:
        confidence = float(relation.get("classification_confidence", 0.0))
    except (TypeError, ValueError):
        confidence = -1.0
    if not 0.0 <= confidence <= 1.0:
        errors.append("classification_confidence must be between 0 and 1")

    return errors


def validate_graph_evidence_relations(state: Dict[str, Any]) -> Dict[str, Any]:
    """Validate evidence relations against the currently known graph/state."""
    graph = state.get("knowledge_graph", {}) if isinstance(state, dict) else {}
    evidence_state = state.get("evidence_state", {}) if isinstance(state, dict) else {}
    relations = (
        evidence_state.get("relationships", {})
        if isinstance(evidence_state, dict)
        else {}
    )
    locations = (
        evidence_state.get("locations", {})
        if isinstance(evidence_state, dict)
        else {}
    )

    if not isinstance(relations, dict):
        relations = {}
    if not isinstance(locations, dict):
        locations = {}

    source_ids = []
    propositions = graph.get("propositions", {}) if isinstance(graph, dict) else {}
    if isinstance(propositions, dict):
        for proposition in propositions.values():
            if isinstance(proposition, dict):
                source_ids.extend(proposition.get("source_ids", []) or [])

    report = {"checked": 0, "valid": 0, "errors": []}
    for relation in relations.values():
        report["checked"] += 1
        errors = validate_evidence_relation(
            relation,
            source_ids=source_ids,
            proposition_ids=list(propositions.keys()) if isinstance(propositions, dict) else [],
            location_ids=list(locations.keys()),
        )
        if errors:
            report["errors"].append({
                "evidence_relation_id": relation.get("evidence_relation_id"),
                "errors": errors,
            })
        else:
            report["valid"] += 1
    return report
