#!/usr/bin/env python3
"""Read-only audit for conservative Stage 7 relationship candidates."""

from __future__ import annotations

from core.relationship_candidates import candidate_relationships

P1 = "11111111-1111-4111-8111-111111111111"
P2 = "22222222-2222-4222-8222-222222222222"
P3 = "33333333-3333-4333-8333-333333333333"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    graph = {
        "concepts": {
            P1: {"concept_id": P1, "name": "Finite Element Method", "source_ids": ["s1"],
                 "relationship_hints": [{"target_concept_id": P2, "type": "generalizes", "reason": "Explicit source hint."}]},
            P2: {"concept_id": P2, "name": "Galerkin Method", "source_ids": ["s2"]},
            P3: {"concept_id": P3, "name": "Unrelated", "source_ids": ["s3"],
                 "relationship_hints": [{"target_concept_id": "missing", "type": "related_to"}]},
        },
        "propositions": {},
        "relationships": {},
    }

    changed = candidate_relationships(graph)
    check(changed == 1, "Unexpected candidate count.")
    candidates = graph["relationship_candidates"]
    check(len(candidates) == 1, "Invalid relationship candidate was stored.")
    candidate = next(iter(candidates.values()))
    check(candidate["source_id"] == P1, "Wrong candidate source.")
    check(candidate["target_id"] == P2, "Wrong candidate target.")
    check(candidate["type"] == "generalizes", "Wrong relationship type.")
    check(candidate["status"] == "candidate", "Candidate became authoritative.")
    check(not graph["relationships"], "Candidate unexpectedly entered authoritative relationships.")

    changed_again = candidate_relationships(graph)
    check(changed_again == 0, "Candidate generation was not idempotent.")

    print("Stage 7 candidate relationship audit")
    print("====================================")
    print("PASS: explicit hints, reference validation, non-authoritative storage, and idempotence passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
