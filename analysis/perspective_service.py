#!/usr/bin/env python3
"""Graph-native service for bounded scientific perspective comparison."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from analysis.perspective_candidates import candidate_pairs
from analysis.perspective_analyzer import compare_propositions
from analysis.perspective_ledger import record_comparisons
from core.graph_repository import upsert_relationship


_RELATIONSHIP_MAP = {
    "complementary": "complements",
    "alternative": "alternative_to",
    "different_framework": "contrasts_with",
    "appears_to_contradict": "appears_to_contradict",
    "contradicts_under_same_assumptions": "contradicts_under_same_assumptions",
    "conditionally_supported": "conditional_on",
}


def _record_graph_relationship(graph: Dict[str, Any], record: Dict[str, Any]) -> Optional[str]:
    comparison = record.get("comparison", {})
    if not isinstance(comparison, dict):
        return None

    relation_type = _RELATIONSHIP_MAP.get(str(comparison.get("relationship", "")).strip().lower())
    if not relation_type:
        return None

    proposition_ids = record.get("proposition_ids", [])
    if not isinstance(proposition_ids, list) or len(proposition_ids) != 2:
        return None
    first_id, second_id = (str(value) for value in proposition_ids)
    propositions = graph.get("propositions", {})
    if (
        not isinstance(propositions, dict)
        or first_id not in propositions
        or second_id not in propositions
    ):
        return None

    context_basis = record.get("context_basis", {})
    context_a = context_basis.get("context_a", {}) if isinstance(context_basis, dict) else {}
    context_b = context_basis.get("context_b", {}) if isinstance(context_basis, dict) else {}
    assumptions = list(dict.fromkeys(
        (context_a.get("assumptions", []) if isinstance(context_a, dict) else [])
        + (context_b.get("assumptions", []) if isinstance(context_b, dict) else [])
    ))
    conditions = list(dict.fromkeys(
        (context_a.get("conditions", []) if isinstance(context_a, dict) else [])
        + (context_b.get("conditions", []) if isinstance(context_b, dict) else [])
    ))
    frameworks = [
        str(context_a.get("framework", "")).strip() if isinstance(context_a, dict) else "",
        str(context_b.get("framework", "")).strip() if isinstance(context_b, dict) else "",
    ]
    return upsert_relationship(
        graph,
        source_id=first_id,
        target_id=second_id,
        relation_type=relation_type,
        proposition_ids=[first_id, second_id],
        source_ids=record.get("source_ids", []),
        confidence=float(comparison.get("confidence", 0.0) or 0.0),
        framework="; ".join(item for item in frameworks if item),
        assumptions=assumptions,
        conditions=conditions,
        reason=str(comparison.get("reason", "")),
    )


def _targeted_pairs(
    propositions: Dict[str, Dict[str, Any]],
    proposition_ids: List[str],
    *,
    max_pairs: int,
) -> tuple[List[tuple[Dict[str, Any], Dict[str, Any]]], int]:
    """Return validated target pairs, falling back to deterministic discovery when needed."""
    ids = []
    seen = set()
    for value in proposition_ids:
        value = str(value).strip()
        if value and value in propositions and value not in seen:
            ids.append(value)
            seen.add(value)

    if len(ids) >= 2:
        pairs = []
        for index, left_id in enumerate(ids):
            for right_id in ids[index + 1:]:
                pairs.append((propositions[left_id], propositions[right_id]))
                if len(pairs) >= max(0, int(max_pairs)):
                    return pairs, len(pairs)
        return pairs, len(pairs)

    discovered = candidate_pairs(
        list(propositions.values()),
        max_pairs=max(0, int(max_pairs)),
        minimum_overlap=0.15,
    )
    return discovered, len(discovered)


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
    target_proposition_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Compare graph propositions without creating synthetic propositions."""
    graph = state.get("knowledge_graph", {}) if isinstance(state, dict) else {}
    if not isinstance(graph, dict):
        return {"candidates": 0, "compared": 0, "skipped": 0, "relationships_added": 0, "records": []}

    propositions = graph.get("propositions", {})
    if not isinstance(propositions, dict):
        return {"candidates": 0, "compared": 0, "skipped": 0, "relationships_added": 0, "records": []}

    target_ids = target_proposition_ids or []
    if target_ids:
        pairs, candidate_count = _targeted_pairs(
            propositions,
            target_ids,
            max_pairs=max(0, int(max_pairs)),
        )
    else:
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
        candidate_count = len(pairs)

    results: List[Dict[str, Any]] = []
    skipped = 0
    relationships_added = 0

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
        if _record_graph_relationship(graph, comparison):
            relationships_added += 1

    record_comparisons(
        state,
        results,
        max_records=max_records,
    )

    state["knowledge_graph"] = graph
    state["last_perspective_analysis"] = {
        "candidates": candidate_count,
        "compared": len(results),
        "skipped": skipped,
        "relationships_added": relationships_added,
        "targeted": bool(target_ids),
    }

    return {
        "candidates": candidate_count,
        "compared": len(results),
        "skipped": skipped,
        "relationships_added": relationships_added,
        "records": results,
    }
