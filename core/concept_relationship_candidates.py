#!/usr/bin/env python3
"""Deterministic candidate concept-pair selection from existing graph evidence."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


def candidate_concept_pairs(
    graph: Dict[str, Any],
    *,
    max_pairs: int = 12,
) -> List[Tuple[str, str]]:
    """Select concept pairs that co-occur in asserted proposition membership.

    This proposes pairs for later semantic analysis; it never asserts a graph
    relationship and never treats lexical similarity as a scientific relation.
    """
    concepts = graph.get("concepts", {}) if isinstance(graph, dict) else {}
    propositions = graph.get("propositions", {}) if isinstance(graph, dict) else {}
    relationships = graph.get("relationships", {}) if isinstance(graph, dict) else {}
    if not isinstance(concepts, dict) or not isinstance(propositions, dict):
        return []

    asserted_links: Dict[str, set[str]] = {str(cid): set() for cid in concepts}
    pair_weight: Dict[Tuple[str, str], int] = {}

    for proposition in propositions.values():
        if not isinstance(proposition, dict):
            continue
        ids = [
            str(value).strip()
            for value in proposition.get("concept_ids", []) or []
            if str(value).strip() in concepts
        ]
        ids = sorted(set(ids))
        for concept_id in ids:
            asserted_links.setdefault(concept_id, set()).add(
                str(proposition.get("proposition_id", ""))
            )
        for index, left in enumerate(ids):
            for right in ids[index + 1:]:
                pair = (left, right)
                pair_weight[pair] = pair_weight.get(pair, 0) + 1

    # Do not spend work on concept pairs already connected by an authoritative
    # relationship of the same endpoint pair, regardless of relation type.
    connected = set()
    if isinstance(relationships, dict):
        for relation in relationships.values():
            if not isinstance(relation, dict):
                continue
            left = str(relation.get("source_id", "")).strip()
            right = str(relation.get("target_id", "")).strip()
            if left in concepts and right in concepts:
                connected.add(tuple(sorted((left, right))))

    ranked = [
        (weight, left, right)
        for (left, right), weight in pair_weight.items()
        if tuple(sorted((left, right))) not in connected
    ]
    ranked.sort(key=lambda row: (-row[0], row[1], row[2]))
    return [(left, right) for _, left, right in ranked[: max(0, int(max_pairs))]]
