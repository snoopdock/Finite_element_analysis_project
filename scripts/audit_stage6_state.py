#!/usr/bin/env python3
"""Read-only Stage 6 graph-population audit.

Run from the repository root:
    python scripts/audit_stage6_state.py

Uses an in-memory legacy knowledge base and does not call external services.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.graph_state import ensure_graph_state
from core.knowledge_graph import normalize_graph, validate_graph_references, normalize_uuid


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        p_source = "paper-1"
        state = {
            "knowledge_base": {
                "concepts": [
                    {"name": "Galerkin method", "source_ids": [p_source]},
                    {"name": "Finite element method", "source_ids": [p_source]},
                ],
                "rules": [
                    {
                        "rule": "The formulation is stable under the stated assumptions.",
                        "source_ids": [p_source],
                        "framework": "linear formulation",
                        "assumptions": ["small deformation"],
                    },
                ],
                "equations": [],
                "procedures": [],
            },
            "knowledge_graph": {
                "concepts": {},
                "propositions": {},
                "relationships": {},
                "concept_history": [],
            },
        }

        ensure_graph_state(state)
        graph = state["knowledge_graph"]

        concepts_before = dict(graph["concepts"])
        propositions_before = dict(graph["propositions"])
        history_before = list(graph["concept_history"])

        check(len(concepts_before) == 2, "Expected two bridged concepts.")
        check(len(propositions_before) == 1, "Expected one bridged proposition.")
        check(not graph["relationships"], "Bridge should not fabricate relationships.")
        check(not validate_graph_references(graph), "Initial bridged graph has reference violations.")

        for concept in concepts_before.values():
            check(normalize_uuid(concept.get("concept_id")) is not None, "Concept ID is not a UUID.")
            check(p_source in concept.get("source_ids", []), "Concept provenance was lost.")

        proposition = next(iter(propositions_before.values()))
        check(normalize_uuid(proposition.get("proposition_id")) is not None, "Proposition ID is not a UUID.")
        check(proposition.get("source_ids") == [p_source], "Proposition provenance was lost.")
        check(proposition.get("framework") == "linear formulation", "Framework context was lost.")
        check(proposition.get("assumptions") == ["small deformation"], "Assumption context was lost.")
        check(proposition.get("context", {}).get("framework") == "linear formulation", "Normalized context was lost.")

        ensure_graph_state(state)
        graph_after = state["knowledge_graph"]

        check(set(graph_after["concepts"]) == set(concepts_before), "Concept IDs changed on second synchronization.")
        check(set(graph_after["propositions"]) == set(propositions_before), "Proposition IDs changed on second synchronization.")
        check(graph_after["relationships"] == {}, "Second synchronization created relationships unexpectedly.")
        check(graph_after["concept_history"] == history_before, "Idempotent synchronization changed concept history.")
        check(not validate_graph_references(normalize_graph(graph_after)), "Final graph has reference violations.")

        print("Stage 6 graph-population audit")
        print("==============================")
        print("PASS: legacy concepts/propositions, provenance/context preservation, idempotent synchronization, and no fabricated relationships passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 6 GRAPH AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
