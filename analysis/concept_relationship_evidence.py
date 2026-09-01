#!/usr/bin/env python3
"""Collect source-backed propositions for concept-relationship analysis."""

from __future__ import annotations

from typing import Any, Dict, List


def propositions_for_concept_pair(
    graph: Dict[str, Any],
    concept_a_id: str,
    concept_b_id: str,
    *,
    max_propositions: int = 8,
) -> List[Dict[str, Any]]:
    """Return bounded evidence about either concept, preferring shared evidence.

    Propositions mentioning both concepts are preferred because they directly
    address the pair. When there are too few, propositions about either concept
    are added so relationship analysis is not limited to co-occurrence records.
    """
    propositions = graph.get("propositions", {}) if isinstance(graph, dict) else {}
    if not isinstance(propositions, dict):
        return []

    a_id = str(concept_a_id)
    b_id = str(concept_b_id)
    shared: List[Dict[str, Any]] = []
    separate: List[Dict[str, Any]] = []

    for proposition_id, proposition in propositions.items():
        if not isinstance(proposition, dict):
            continue
        statement = str(proposition.get("statement", "")).strip()
        if not statement:
            continue
        concept_ids = {str(value).strip() for value in proposition.get("concept_ids", []) or []}
        source_ids = {
            str(value).strip()
            for value in proposition.get("source_ids", []) or []
            if str(value).strip()
        }
        if a_id in concept_ids and b_id in concept_ids:
            shared.append((len(source_ids), str(proposition_id), proposition))
        elif a_id in concept_ids or b_id in concept_ids:
            separate.append((len(source_ids), str(proposition_id), proposition))

    shared.sort(key=lambda item: (-item[0], item[1]))
    separate.sort(key=lambda item: (-item[0], item[1]))

    limit = max(0, int(max_propositions))
    selected = [item[2] for item in shared[:limit]]
    if len(selected) < limit:
        selected_ids = {str(item.get("proposition_id", "")) for item in selected}
        for _, proposition_id, proposition in separate:
            if proposition_id in selected_ids:
                continue
            selected.append(proposition)
            if len(selected) >= limit:
                break
    return selected
