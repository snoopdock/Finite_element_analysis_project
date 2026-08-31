#!/usr/bin/env python3
"""Read-only audit for Stage 7 concept-pair candidate discovery."""

from __future__ import annotations

from core.concept_relationship_candidates import candidate_concept_pairs

P1 = "11111111-1111-4111-8111-111111111111"
P2 = "22222222-2222-4222-8222-222222222222"
P3 = "33333333-3333-4333-8333-333333333333"
P4 = "44444444-4444-4444-8444-444444444444"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    graph = {
        "concepts": {
            P1: {"concept_id": P1, "name": "FEM"},
            P2: {"concept_id": P2, "name": "Galerkin"},
            P3: {"concept_id": P3, "name": "Stabilization"},
            P4: {"concept_id": P4, "name": "Mesh"},
        },
        "propositions": {
            "55555555-5555-4555-8555-555555555555": {
                "proposition_id": "55555555-5555-4555-8555-555555555555",
                "concept_ids": [P1, P2, P3],
            },
            "66666666-6666-4666-8666-666666666666": {
                "proposition_id": "66666666-6666-4666-8666-666666666666",
                "concept_ids": [P1, P2],
            },
        },
        "relationships": {},
    }

    pairs = candidate_concept_pairs(graph, max_pairs=5)
    check((P1, P2) in pairs, "Expected co-occurring concept pair was not selected.")
    check((P1, P3) in pairs, "Expected secondary concept pair was not selected.")
    check((P2, P3) in pairs, "Expected secondary concept pair was not selected.")
    check(len(pairs) <= 5, "Concept-pair bound was exceeded.")

    graph["relationships"] = {
        "77777777-7777-4777-8777-777777777777": {
            "relationship_id": "77777777-7777-4777-8777-777777777777",
            "source_id": P1,
            "target_id": P2,
            "type": "related_to",
        }
    }
    pairs_after = candidate_concept_pairs(graph, max_pairs=5)
    check((P1, P2) not in pairs_after, "Existing authoritative relation was rediscovered.")

    print("Stage 7 concept-pair candidate audit")
    print("====================================")
    print("PASS: evidence-derived pairing, deterministic bounds, and existing-edge exclusion passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
