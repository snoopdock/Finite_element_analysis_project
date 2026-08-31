#!/usr/bin/env python3
"""Promote only explicitly supplied concept membership into graph propositions."""

from __future__ import annotations

import re
from typing import Any, Dict, List


def _normalize(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _explicit_ids(value: Any) -> List[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    result = []
    seen = set()
    for item in value:
        item = str(item).strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def apply_explicit_membership(state: Dict[str, Any]) -> int:
    """Apply concept membership only when legacy records explicitly name concepts."""
    graph = state.get("knowledge_graph", {})
    kb = state.get("knowledge_base", {})
    if not isinstance(graph, dict) or not isinstance(kb, dict):
        return 0

    concepts = graph.get("concepts", {})
    propositions = graph.get("propositions", {})
    if not isinstance(concepts, dict) or not isinstance(propositions, dict):
        return 0

    concept_by_name = {
        _normalize(concept.get("name")): str(concept_id)
        for concept_id, concept in concepts.items()
        if isinstance(concept, dict) and concept.get("name")
    }
    changed = 0

    for category in ("equations", "rules", "procedures"):
        records = kb.get(category, [])
        if not isinstance(records, list):
            continue
        for item in records:
            if not isinstance(item, dict) or not item.get("proposition_id"):
                continue
            proposition_id = str(item["proposition_id"])
            proposition = propositions.get(proposition_id)
            if not isinstance(proposition, dict):
                continue

            ids = [value for value in _explicit_ids(item.get("concept_ids", [])) if value in concepts]
            names = _explicit_ids(item.get("concept_names", []))
            ids.extend(
                concept_by_name[name]
                for name in names
                if _normalize(name) in concept_by_name
            )
            ids = sorted(set(ids))
            if ids and ids != sorted(set(proposition.get("concept_ids", []))):
                proposition["concept_ids"] = ids
                changed += 1

    return changed
