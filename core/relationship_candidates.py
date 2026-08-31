#!/usr/bin/env python3
"""Conservative candidate relationships between existing scientific concepts."""

from __future__ import annotations

from typing import Any, Dict, List

_ALLOWED = {
    "subconcept_of",
    "specializes",
    "generalizes",
    "alternative_to",
    "complements",
    "related_to",
}


def _clean_ids(values: Any) -> List[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    result = []
    seen = set()
    for value in values:
        value = str(value).strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def candidate_relationships(graph: Dict[str, Any]) -> int:
    """Record explicit relationship hints as non-authoritative graph candidates.

    Accepted hint records may be supplied on a concept as ``relationship_hints``
    with ``target_concept_id`` and ``type``. No relationship is asserted here.
    """
    concepts = graph.get("concepts", {}) if isinstance(graph, dict) else {}
    if not isinstance(concepts, dict):
        return 0

    candidates = graph.setdefault("relationship_candidates", {})
    if not isinstance(candidates, dict):
        candidates = {}
        graph["relationship_candidates"] = candidates

    changed = 0
    for source_id, concept in concepts.items():
        if not isinstance(concept, dict):
            continue
        hints = concept.get("relationship_hints", [])
        if not isinstance(hints, list):
            continue
        for hint in hints:
            if not isinstance(hint, dict):
                continue
            target_id = str(hint.get("target_concept_id", "")).strip()
            relation_type = str(hint.get("type", "")).strip()
            if not target_id or target_id == str(source_id) or target_id not in concepts:
                continue
            if relation_type not in _ALLOWED:
                continue

            key = "|".join(sorted((str(source_id), target_id))) + "|" + relation_type
            record = {
                "candidate_id": key,
                "source_id": str(source_id),
                "target_id": target_id,
                "type": relation_type,
                "source_ids": _clean_ids(hint.get("source_ids", concept.get("source_ids", []))),
                "reason": str(hint.get("reason", "")).strip(),
                "status": "candidate",
            }
            if candidates.get(key) != record:
                candidates[key] = record
                changed += 1

    return changed
