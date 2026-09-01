#!/usr/bin/env python3
"""Bounded service for proposing relationships between scientific concepts."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.concept_relationship_candidates import candidate_concept_pairs
from analysis.concept_relationship_analyzer import analyze_concept_relationship
from analysis.concept_relationship_evidence import propositions_for_concept_pair
from analysis.concept_relationship_ledger import record_proposals


def analyze_candidate_concepts(
    state: Dict[str, Any],
    provider,
    parser,
    *,
    max_pairs: int = 2,
    max_propositions_per_pair: int = 8,
    model: Optional[str] = None,
    max_tokens: int = 650,
    max_records: int = 200,
) -> Dict[str, Any]:
    """Analyze a bounded set of concept pairs using source-backed propositions."""
    graph = state.get("knowledge_graph", {}) if isinstance(state, dict) else {}
    if not isinstance(graph, dict):
        return {"candidates": 0, "analyzed": 0, "skipped": 0, "recorded": 0, "records": []}

    pairs = candidate_concept_pairs(graph, max_pairs=max(0, int(max_pairs)))
    concepts = graph.get("concepts", {})
    if not isinstance(concepts, dict):
        return {"candidates": len(pairs), "analyzed": 0, "skipped": 0, "recorded": 0, "records": []}

    records: List[Dict[str, Any]] = []
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

        propositions = propositions_for_concept_pair(
            graph,
            concept_a_id,
            concept_b_id,
            max_propositions=max(0, int(max_propositions_per_pair)),
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

    recorded = record_proposals(state, records, max_records=max(0, int(max_records)))
    state["last_concept_relationship_analysis"] = {
        "candidates": len(pairs),
        "analyzed": len(records),
        "skipped": skipped,
        "recorded": recorded,
    }
    return {
        "candidates": len(pairs),
        "analyzed": len(records),
        "skipped": skipped,
        "recorded": recorded,
        "records": records,
    }
