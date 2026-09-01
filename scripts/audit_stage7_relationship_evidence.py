#!/usr/bin/env python3
"""Read-only audit for Stage 7 concept relationship evidence selection."""

from __future__ import annotations

from analysis.concept_relationship_evidence import propositions_for_concept_pair

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
P_AB = "33333333-3333-4333-8333-333333333333"
P_A = "44444444-4444-4444-8444-444444444444"
P_B = "55555555-5555-4555-8555-555555555555"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    graph = {
        "propositions": {
            P_A: {"proposition_id": P_A, "statement": "Evidence about A", "concept_ids": [A], "source_ids": ["s1"]},
            P_B: {"proposition_id": P_B, "statement": "Evidence about B", "concept_ids": [B], "source_ids": ["s2"]},
            P_AB: {"proposition_id": P_AB, "statement": "Direct evidence linking A and B", "concept_ids": [A, B], "source_ids": ["s3"]},
        }
    }

    selected = propositions_for_concept_pair(graph, A, B, max_propositions=3)
    ids = [item["proposition_id"] for item in selected]
    check(ids[0] == P_AB, "Shared proposition was not preferred.")
    check(P_A in ids and P_B in ids, "Separate concept evidence was omitted.")
    check(len(selected) == 3, "Evidence selection exceeded requested limit.")

    selected_small = propositions_for_concept_pair(graph, A, B, max_propositions=2)
    check(len(selected_small) == 2, "Small evidence limit was not enforced.")
    check(selected_small[0]["proposition_id"] == P_AB, "Shared evidence lost priority under smaller limit.")

    empty = propositions_for_concept_pair(graph, A, B, max_propositions=0)
    check(empty == [], "Zero evidence limit did not return an empty list.")

    print("Stage 7 concept relationship evidence audit")
    print("===========================================")
    print("PASS: shared evidence priority, separate-concept evidence fallback, and bounds passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
