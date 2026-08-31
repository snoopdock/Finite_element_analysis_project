#!/usr/bin/env python3
"""Read-only Stage 6B audit for conservative concept linking.

Run from the repository root:
    python scripts/audit_stage6_concept_linking.py

Uses in-memory data only and does not call external services.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.concept_linking import candidate_concept_links


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        c1 = "11111111-1111-4111-8111-111111111111"
        c2 = "22222222-2222-4222-8222-222222222222"
        p1 = "33333333-3333-4333-8333-333333333333"
        graph = {
            "concepts": {
                c1: {"concept_id": c1, "name": "Galerkin method", "type": "method", "aliases": ["Galerkin"]},
                c2: {"concept_id": c2, "name": "finite element method", "type": "method"},
            },
            "propositions": {
                p1: {
                    "proposition_id": p1,
                    "statement": "The Galerkin method is used in the finite element method.",
                    "concept_ids": [],
                }
            },
            "relationships": {},
            "concept_history": [],
        }

        changed = candidate_concept_links(graph)
        proposition = graph["propositions"][p1]
        check(changed == 1, "Expected one proposition to gain candidate links.")
        check(set(proposition.get("candidate_concept_ids", [])) == {c1, c2}, "Exact concept/alias candidates were not found.")
        check(proposition.get("concept_ids") == [], "Candidate links became asserted concept membership.")

        second_changed = candidate_concept_links(graph)
        check(second_changed == 0, "Candidate linking is not idempotent.")
        check(proposition.get("candidate_concept_ids") == [c1, c2], "Candidate link order is not deterministic.")

        graph["propositions"][p1]["statement"] = "The Galerkin-inspired approach is discussed here."
        candidate_concept_links(graph)
        check(graph["propositions"][p1].get("candidate_concept_ids") == [], "Substring matching created a false candidate.")

        print("Stage 6B concept-linking audit")
        print("===============================")
        print("PASS: exact matching, aliases, non-assertive links, deterministic ordering, and idempotence passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 6B CONCEPT LINKING AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
