#!/usr/bin/env python3
"""Read-only Stage 6C audit for explicit concept membership."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.graph_state import ensure_graph_state


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        c1 = "11111111-1111-4111-8111-111111111111"
        c2 = "22222222-2222-4222-8222-222222222222"
        p1 = "33333333-3333-4333-8333-333333333333"
        p2 = "44444444-4444-4444-8444-444444444444"

        state = {
            "knowledge_base": {
                "concepts": [
                    {"name": "Galerkin method", "source_ids": ["s1"]},
                    {"name": "Finite element method", "source_ids": ["s1"]},
                ],
                "rules": [
                    {
                        "proposition_id": p1,
                        "rule": "The formulation uses the Galerkin method.",
                        "source_ids": ["s1"],
                        "concept_names": ["Galerkin method"],
                    },
                    {
                        "proposition_id": p2,
                        "rule": "This proposition has no explicit concept membership.",
                        "source_ids": ["s1"],
                    },
                ],
                "equations": [],
                "procedures": [],
            },
            "knowledge_graph": {
                "concepts": {
                    c1: {"concept_id": c1, "name": "Galerkin method", "type": "method"},
                    c2: {"concept_id": c2, "name": "Finite element method", "type": "method"},
                },
                "propositions": {},
                "relationships": {},
                "concept_history": [],
            },
        }

        ensure_graph_state(state)
        propositions = state["knowledge_graph"]["propositions"]
        first = propositions[p1]
        second = propositions[p2]

        check(first["concept_ids"] == [c1], "Explicit concept_names were not promoted.")
        check(second["concept_ids"] == [], "Missing explicit membership was inferred.")
        check(c1 in first.get("candidate_concept_ids", []) or c1 in first["concept_ids"], "Expected concept was not represented.")
        check(not state["knowledge_graph"]["relationships"], "Membership bridge created a relationship unexpectedly.")

        print("Stage 6C explicit-membership audit")
        print("==================================")
        print("PASS: explicit IDs/names were promoted, missing membership stayed unasserted, and no relationships were fabricated.")
        return 0
    except Exception as exc:
        print(f"STAGE 6C MEMBERSHIP AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
