#!/usr/bin/env python3
"""Read-only audit for Stage 7 relationship-candidate state integration."""

from __future__ import annotations

from core.graph_state import ensure_graph_state, graph_summary

P1 = "11111111-1111-4111-8111-111111111111"
P2 = "22222222-2222-4222-8222-222222222222"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    state = {
        "knowledge_graph": {
            "concepts": {
                P1: {
                    "concept_id": P1,
                    "name": "Finite Element Method",
                    "type": "method",
                    "source_ids": ["source-a"],
                    "relationship_hints": [{
                        "target_concept_id": P2,
                        "type": "generalizes",
                        "source_ids": ["source-a"],
                    }],
                },
                P2: {
                    "concept_id": P2,
                    "name": "Galerkin Method",
                    "type": "method",
                    "source_ids": ["source-b"],
                },
            },
            "propositions": {},
            "relationships": {},
            "concept_history": [],
            "proposition_history": [],
        }
    }

    ensure_graph_state(state)
    graph = state["knowledge_graph"]
    candidates = graph.get("relationship_candidates", {})
    check(len(candidates) == 1, "Expected one relationship candidate.")
    candidate = next(iter(candidates.values()))
    check(candidate["source_id"] == P1, "Candidate source mismatch.")
    check(candidate["target_id"] == P2, "Candidate target mismatch.")
    check(candidate["status"] == "candidate", "Candidate was promoted unexpectedly.")
    check(not graph["relationships"], "Relationship candidate became authoritative.")

    summary = graph_summary(state)
    check(summary["relationship_candidates"] == 1, "Candidate count missing from graph summary.")
    check(summary["violations"] == 0, "Graph contains reference violations.")

    ensure_graph_state(state)
    check(len(state["knowledge_graph"]["relationship_candidates"]) == 1, "Candidate state is not idempotent.")

    print("Stage 7 relationship-candidate state audit")
    print("===========================================")
    print("PASS: state integration, non-authoritative storage, idempotence, and graph-summary checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
