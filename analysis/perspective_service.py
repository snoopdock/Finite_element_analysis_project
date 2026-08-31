#!/usr/bin/env python3
"""Graph-native service for bounded scientific perspective comparison."""

from __future__ import annotations

from typing import Any, Dict, List

from analysis.perspective_candidates import candidate_pairs
from analysis.perspective_analyzer import compare_propositions
from analysis.perspective_ledger import record_comparisons


def compare_graph_propositions(
    state: Dict[str, Any],
    provider,
    parser,
    *,
    max_pairs: int = 4,
    minimum_overlap: float = 0.15,
    max_records: int = 200,
    model: str | None = None,
    max_tokens: int = 600,
) -> Dict[str, Any]:
    """Compare existing graph propositions without creating synthetic propositions."""
    graph = state.get("knowledge_graph", {}) if isinstance(state, dict) else {}
    if not isinstance(graph, dict):
        return {"candidates": 0, "compared": 0, "skipped": 0, "records": []}

    propositions = graph.get("propositions", {})
    if not isinstance(propositions, dict):
        return {"candidates": 0, "compared": 0, "skipped": 0, "records": []}

    records = [
        proposition
        for proposition in propositions.values()
        if isinstance(proposition, dict) and proposition.get("proposition_id")
    ]

    pairs = candidate_pairs(
        records,
        max_pairs=max(0, int(max_pairs)),
        minimum_overlap=float(minimum_overlap),
    )

    results: List[Dict[str, Any]] = []
    skipped = 0

    for first, second in pairs:
        if provider.budget_exhausted():
            skipped += 1
            break

        comparison = compare_propositions(
            first,
            second,
            provider,
            parser,
            model=model,
            max_tokens=max_tokens,
        )

        if comparison.get("skipped"):
            skipped += 1
            continue

        results.append(comparison)

    record_comparisons(
        state,
        results,
        max_records=max_records,
    )

    state["last_perspective_analysis"] = {
        "candidates": len(pairs),
        "compared": len(results),
        "skipped": skipped,
    }

    return {
        "candidates": len(pairs),
        "compared": len(results),
        "skipped": skipped,
        "records": results,
    }
