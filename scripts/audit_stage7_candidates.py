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
                 "relationship_hints": [
                     {"target_concept_id": P2, "type": "generalizes", "reason": "Explicit source hint."},
                     {"target_concept_id": P3, "type": "alternative_to", "reason": "Reverse duplicate test."},
                 ]},
            P2: {"concept_id": P2, "name": "Galerkin Method", "source_ids": ["s2"]},
            P3: {"concept_id": P3, "name": "Unrelated", "source_ids": ["s3"],
                 "relationship_hints": [{"target_concept_id": P1, "type": "alternative_to", "reason": "Same symmetric relation."}]},
        },
        "propositions": {},
        "relationships": {},
    }

    changed = candidate_relationships(graph)
    check(changed == 2, "Unexpected candidate count.")
    candidates = graph["relationship_candidates"]
    check(len(candidates) == 2, "Invalid relationship candidate was stored or symmetric duplicate was created.")

    generalizes = [c for c in candidates.values() if c["type"] == "generalizes"][0]
    check(generalizes["source_id"] == P1, "Directional relationship source changed.")
    check(generalizes["target_id"] == P2, "Directional relationship target changed.")

    alternative = [c for c in candidates.values() if c["type"] == "alternative_to"][0]
    check(alternative["source_id"] < alternative["target_id"], "Symmetric relationship was not canonicalized.")
    check(alternative["status"] == "candidate", "Candidate became authoritative.")
    check(not graph["relationships"], "Candidate unexpectedly entered authoritative relationships.")

    changed_again = candidate_relationships(graph)
    check(changed_again == 0, "Candidate generation was not idempotent.")

    print("Stage 7 candidate relationship audit")
    print("====================================")
    print("PASS: explicit hints, directional/symmetric semantics, validation, non-authoritative storage, and idempotence passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
