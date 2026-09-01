#!/usr/bin/env python3
"""Combined read-only audit for the Stage 7 concept-relationship loop."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.concept_relationship_analyzer import normalize_relationship_proposal
from analysis.concept_relationship_ledger import record_proposal

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
P = "33333333-3333-4333-8333-333333333333"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        state = {
            "knowledge_graph": {
                "concepts": {
                    A: {"concept_id": A, "name": "Concept A"},
                    B: {"concept_id": B, "name": "Concept B"},
                },
                "propositions": {
                    P: {
                        "proposition_id": P,
                        "concept_ids": [A, B],
                        "source_ids": ["source-a", "source-b"],
                        "statement": "A and B are used together under the stated framework.",
                        "context": {"framework": "framework X", "conditions": ["condition Y"]},
                    }
                },
                "relationships": {},
                "relationship_candidates": {},
            }
        }

        proposal = normalize_relationship_proposal({
            "relationship": "complementary",
            "confidence": 0.9,
            "reason": "Evidence links the two concepts without establishing a hierarchy.",
            "source_ids": ["source-a"],
        })
        check(proposal["relationship"] == "complements", "Relationship label normalization failed.")
        check(proposal["confidence"] == 0.9, "Confidence normalization failed.")

        result = {
            "concept_ids": [A, B],
            "proposition_ids": [P],
            "source_ids": ["source-a", "source-b"],
            "proposal": proposal,
            "skipped": False,
        }
        check(record_proposal(state, result, max_records=10), "Valid proposal was not persisted.")
        candidates = state["knowledge_graph"]["relationship_candidates"]
        check(len(candidates) == 1, "Expected one persisted relationship candidate.")
        candidate = next(iter(candidates.values()))
        check(candidate["status"] == "candidate", "Proposal crossed the assertion boundary.")
        check(candidate["proposition_ids"] == [P], "Supporting proposition provenance was lost.")
        check(not state["knowledge_graph"]["relationships"], "Candidate unexpectedly became authoritative.")

        # A later insufficient-evidence result must not erase the existing candidate.
        insufficient = dict(result)
        insufficient["proposal"] = normalize_relationship_proposal({"relationship": "insufficient_evidence"})
        check(not record_proposal(state, insufficient, max_records=10), "Insufficient evidence was persisted as a relationship candidate.")
        check(len(candidates) == 1, "Insufficient evidence unexpectedly changed candidate state.")

        print("Stage 7 concept relationship loop audit")
        print("=========================================")
        print("PASS: semantic normalization, provenance, candidate persistence, assertion boundary, and insufficient-evidence handling passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 7 CONCEPT RELATIONSHIP LOOP AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
