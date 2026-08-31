#!/usr/bin/env python3
"""Read-only audit for the derived Stage 7 concept branch state."""

from __future__ import annotations

from core.branch_state import refresh_branch_view

ROOT = "11111111-1111-4111-8111-111111111111"
CHILD = "22222222-2222-4222-8222-222222222222"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    state = {
        "knowledge_graph": {
            "concepts": {
                ROOT: {"concept_id": ROOT, "name": "FEM", "parent_concept_ids": []},
                CHILD: {"concept_id": CHILD, "name": "Galerkin", "parent_concept_ids": [ROOT]},
            },
            "propositions": {},
            "relationships": {},
        }
    }

    view = refresh_branch_view(state)
    check(state.get("concept_branch_view") == view, "Derived branch view was not persisted.")
    check(view["roots"] == [ROOT], "Unexpected root in branch view.")
    check(view["nodes"][CHILD]["depth"] == 1, "Unexpected child depth.")
    check(not state["knowledge_graph"]["relationships"], "Branch view changed authoritative relationships.")

    print("Stage 7 branch-state audit")
    print("==========================")
    print("PASS: derived branch view, explicit hierarchy, and non-authoritative separation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
