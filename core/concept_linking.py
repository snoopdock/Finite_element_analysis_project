#!/usr/bin/env python3
"""Conservative candidate linking between propositions and existing concepts."""

from __future__ import annotations

import re
from typing import Any, Dict, List


def _normalize(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _aliases(concept: Dict[str, Any]) -> List[str]:
    values = [concept.get("name", "")]
    values.extend(concept.get("aliases", []) if isinstance(concept.get("aliases", []), list) else [])
    result = []
    seen = set()
    for value in values:
        normalized = _normalize(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def candidate_concept_links(graph: Dict[str, Any]) -> int:
    """Attach deterministic candidate concept IDs without asserting membership."""
    concepts = graph.get("concepts", {}) if isinstance(graph, dict) else {}
    propositions = graph.get("propositions", {}) if isinstance(graph, dict) else {}
    if not isinstance(concepts, dict) or not isinstance(propositions, dict):
        return 0

    concept_terms = [
        (str(concept_id), alias)
        for concept_id, concept in concepts.items()
        if isinstance(concept, dict)
        for alias in _aliases(concept)
    ]

    changed = 0
    for proposition in propositions.values():
        if not isinstance(proposition, dict):
            continue
        statement = _normalize(proposition.get("statement", ""))
        if not statement:
            continue

        existing = proposition.get("concept_ids", [])
        asserted = set(str(value) for value in existing if value)
        candidates = []
        for concept_id, alias in concept_terms:
            if concept_id in asserted:
                continue
            if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", statement):
                candidates.append(concept_id)

        candidate_ids = sorted(set(candidates))
        old_candidate_ids = proposition.get("candidate_concept_ids", [])
        if candidate_ids != sorted(set(str(value) for value in old_candidate_ids if value)):
            proposition["candidate_concept_ids"] = candidate_ids
            changed += 1

    return changed
