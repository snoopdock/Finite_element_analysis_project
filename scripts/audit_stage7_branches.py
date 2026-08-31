#!/usr/bin/env python3
"""Read-only audit for the Stage 7 explicit concept-branch view."""

from __future__ import annotations

from core.concept_branches import concept_branches

R = "11111111-1111-4111-8111-111111111111"
A = "22222222-2222-4222-8222-222222222222"
B = "33333333-3333-4333-8333-333333333333"
C = "44444444-4444-4444-8444-444444444444"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    graph = {
        "concepts": {
            R: {"concept_id": R, "name": "FEM", "parent_concept_ids": []},
            A: {"concept_id": A, "name": "Structural", "parent_concept_ids": [R]},
            B: {"concept_id": B, "name": "Fluid", "parent_concept_ids": [R]},
            C: {"concept_id": C, "name": "Stabilization", "parent_concept_ids": [A]},
        }
    }

    result = concept_branches(graph)
    check(result["roots"] == [R], "Root concept not detected.")
    check(result["nodes"][R]["children"] == [A, B], "Root branches are not deterministic.")
    check(result["nodes"][C]["depth"] == 2, "Nested branch depth is incorrect.")
    check(not result["cycles"], "Unexpected hierarchy cycle detected.")
    check(not result["missing_parent_references"], "Unexpected missing parent reference.")

    graph["concepts"][C]["parent_concept_ids"] = ["55555555-5555-4555-8555-555555555555"]
    missing = concept_branches(graph)
    check(missing["missing_parent_references"], "Missing parent reference was not reported.")

    graph["concepts"][C]["parent_concept_ids"] = [R]
    graph["concepts"][R]["parent_concept_ids"] = [C]
    cyclic = concept_branches(graph)
    check(cyclic["cycles"], "Hierarchy cycle was not detected.")

    print("Stage 7 concept branch audit")
    print("============================")
    print("PASS: explicit hierarchy, deterministic branches, depth, missing-parent, and cycle detection passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
