#!/usr/bin/env python3
"""Bounded service for proposing relationships between scientific concepts."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.concept_relationship_candidates import candidate_concept_pairs
from analysis.concept_relationship_analyzer import analyze_concept_relationship


def _concept_propositions(
    graph: Dict[str, Any],
    concept_a_id: str,
    concept_b_id: str,
    *,
    max_propositions: int,
) -> List[Dict[str, Any]]:
    propositions = graph.get("propositions", {}) if isinstance(graph, dict) else {}
    if not isinstance(propositions, dict):
        return []

    wanted = {str(concept_a_id), str(concept_b_id)}
    candidates: List[Tuple[int, str, Dict[str, Any]]] = []
    for proposition_id, proposition in propositions.items():
        if not isinstance(proposition, dict):
            continue
        concept_ids = {str(value).strip() for value in proposition.get("concept_ids", []) or []}
        if not wanted.issubset(concept_ids):
            continue
        source_count = len({str(value).strip() for value in proposition.get("source_ids", []) or [] if str(value).strip()})
        candidates.append((source_count, str(proposition_id), proposition))

    candidates.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in candidates[: max(0, int(max_propositions))]]


def analyze_candidate_concepts(
    state: Dict[str, Any],
    provider,
    parser,
    *,
    max_pairs: int = 2,
    max_propositions_per_pair: int = 8,
    model: Optional[str] = None,
    max_tokens: int = 650,
) -> Dict[str, Any]:
    """Analyze a bounded set of concept pairs using existing source-backed propositions."""
    graph = state.get("knowledge_graph", {}) if isinstance(state, dict) else {}
    if not isinstance(graph, dict):
        return {"candidates": 0, "analyzed": 0, "skipped": 0, "records": []}

    pairs = candidate_concept_pairs(graph, max_pairs=max(0, int(max_pairs)))
    concepts = graph.get("concepts", {})
    if not isinstance(concepts, dict):
        return {"candidates": len(pairs), "analyzed": 0, "skipped": 0, "records": []}

    records = []
    skipped = 0
    for concept_a_id, concept_b_id in pairs:
        if provider.budget_exhausted():
            skipped += 1
            break
        concept_a = concepts.get(concept_a_id)
        concept_b = concepts.get(concept_b_id)
        if not isinstance(concept_a, dict) or not isinstance(concept_b, dict):
            skipped += 1
            continue

        propositions = _concept_propositions(
            graph,
            concept_a_id,
            concept_b_id,
            max_propositions=max_propositions_per_pair,
        )
        if not propositions:
            skipped += 1
            continue

        result = analyze_concept_relationship(
            concept_a,
            concept_b,
            propositions,
            provider,
            parser,
            model=model,
            max_tokens=max_tokens,
        )
        if result.get("skipped"):
            skipped += 1
            continue
        records.append(result)

    state["last_concept_relationship_analysis"] = {
        "candidates": len(pairs),
        "analyzed": len(records),
        "skipped": skipped,
    }
    return {
        "candidates": len(pairs),
        "analyzed": len(records),
        "skipped": skipped,
        "records": records,
    }
