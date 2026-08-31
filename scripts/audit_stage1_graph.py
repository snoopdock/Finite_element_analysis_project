#!/usr/bin/env python3
"""Runtime audit for the Stage 1 provenance-aware graph state.

Run from the repository root:
    python scripts/audit_stage1_graph.py

The audit is read-only. It checks graph normalization/reference integrity,
ID uniqueness, proposition/concept separation, and the Stage 1 contract.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.knowledge_graph import normalize_graph, validate_graph_references


STATE_PATH = ROOT / "state" / "current_state.json"


def _load_state() -> dict:
    if not STATE_PATH.exists():
        raise FileNotFoundError(f"State file not found: {STATE_PATH}")
    with STATE_PATH.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("State root must be a JSON object.")
    return value


def _audit_graph(graph: dict) -> list[str]:
    errors: list[str] = []
    normalize_graph(graph)
    errors.extend(validate_graph_references(graph))

    concepts = graph.get("concepts", {})
    propositions = graph.get("propositions", {})
    relationships = graph.get("relationships", {})

    if not isinstance(concepts, dict):
        errors.append("Graph concepts collection is not a dictionary.")
    if not isinstance(propositions, dict):
        errors.append("Graph propositions collection is not a dictionary.")
    if not isinstance(relationships, dict):
        errors.append("Graph relationships collection is not a dictionary.")

    concept_ids = list(concepts.keys()) if isinstance(concepts, dict) else []
    proposition_ids = list(propositions.keys()) if isinstance(propositions, dict) else []
    relationship_ids = list(relationships.keys()) if isinstance(relationships, dict) else []

    if len(concept_ids) != len(set(concept_ids)):
        errors.append("Duplicate concept IDs detected.")
    if len(proposition_ids) != len(set(proposition_ids)):
        errors.append("Duplicate proposition IDs detected.")
    if len(relationship_ids) != len(set(relationship_ids)):
        errors.append("Duplicate relationship IDs detected.")

    overlap = set(concept_ids) & set(proposition_ids)
    if overlap:
        errors.append(f"Concept/proposition ID collision(s): {sorted(overlap)}")

    for proposition_id, proposition in propositions.items() if isinstance(propositions, dict) else []:
        if not str(proposition.get("statement", "")).strip():
            errors.append(f"Proposition {proposition_id} has an empty statement.")
        if proposition.get("concept_ids") is None:
            errors.append(f"Proposition {proposition_id} has no concept_ids field.")
        if proposition.get("source_ids") is None:
            errors.append(f"Proposition {proposition_id} has no source_ids field.")

    for concept_id, concept in concepts.items() if isinstance(concepts, dict) else []:
        if not str(concept.get("name", "")).strip():
            errors.append(f"Concept {concept_id} has an empty name.")
        if concept.get("source_ids") is None:
            errors.append(f"Concept {concept_id} has no source_ids field.")

    return errors


def main() -> int:
    try:
        state = _load_state()
        graph = state.get("knowledge_graph", {})
        if not isinstance(graph, dict):
            raise ValueError("knowledge_graph must be a JSON object.")
        errors = _audit_graph(graph)
    except Exception as exc:
        print(f"STAGE 1 GRAPH AUDIT: ERROR: {exc}")
        return 2

    counts = {
        "concepts": len(graph.get("concepts", {})),
        "propositions": len(graph.get("propositions", {})),
        "relationships": len(graph.get("relationships", {})),
        "history_events": len(graph.get("concept_history", [])),
    }

    print("Stage 1 graph runtime audit")
    print("===========================")
    for name, value in counts.items():
        print(f"{name}: {value}")

    if errors:
        print("\nFAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print("\nPASS: graph state satisfies the Stage 1 structural audit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
