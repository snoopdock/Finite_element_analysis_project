#!/usr/bin/env python3
"""Read-only audit for the Stage 7 concept-relationship proposal ledger."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.concept_relationship_ledger import record_proposal

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
P = "33333333-3333-4333-8333-333333333333"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def result(relationship: str = "complementary"):
    return {
        "concept_ids": [B, A],
        "source_ids": ["source-b"],
        "proposition_ids": [P],
        "skipped": False,
        "proposal": {
            "relationship": relationship,
            "confidence": 0.87,
            "reason": "Source-backed relation.",
            "source_ids": ["source-a", "source-b"],
        },
    }


def main() -> int:
    try:
        state = {"knowledge_graph": {"relationship_candidates": {}}}
        check(record_proposal(state, result()) is True, "Valid proposal was not recorded.")
        candidates = state["knowledge_graph"]["relationship_candidates"]
        check(len(candidates) == 1, "Unexpected proposal count.")
        candidate = next(iter(candidates.values()))
        check(candidate["source_id"] == A, "Symmetric proposal was not canonicalized.")
        check(candidate["target_id"] == B, "Symmetric proposal target was not canonicalized.")
        check(candidate["type"] == "complements", "Semantic relation was not normalized.")
        check(candidate["source_ids"] == ["source-a", "source-b"], "Proposal provenance was not retained.")
        check(candidate["proposition_ids"] == [P], "Proposition provenance was not retained.")
        check(candidate["status"] == "candidate", "Proposal became authoritative.")
        check(not state["knowledge_graph"].get("relationships"), "Proposal unexpectedly created an authoritative relationship.")

        # Repeating the same proposal must replace the same deterministic record.
        check(record_proposal(state, result()) is True, "Repeated proposal was not accepted.")
        check(len(state["knowledge_graph"]["relationship_candidates"]) == 1, "Repeated proposal duplicated state.")

        # Insufficient evidence is a comparison state, not a relationship candidate.
        check(record_proposal(state, result("insufficient_evidence")) is False, "Insufficient evidence became a proposal.")

        zero_state = {"knowledge_graph": {"relationship_candidates": {"seed": {"status": "candidate"}}}}
        check(record_proposal(zero_state, result(), max_records=0) is False, "Zero record limit did not reject the record.")
        check(not zero_state["knowledge_graph"]["relationship_candidates"], "Zero record limit did not clear the proposal set.")

        existing = {"status": "promoted", "relationship_id": "rel-1"}
        state2 = {"knowledge_graph": {"relationship_candidates": {
            "relprop-existing": existing
        }}}
        check(record_proposal(state2, result(), max_records=200) is True, "Valid proposal could not be recorded beside existing state.")
        check(state2["knowledge_graph"]["relationship_candidates"]["relprop-existing"] is existing,
              "Unrelated existing candidate was modified.")

        print("Stage 7 concept relationship ledger audit")
        print("==========================================")
        print("PASS: bounded proposal persistence, symmetry, normalization, provenance, non-authoritative storage, and zero-limit handling passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 7 RELATIONSHIP LEDGER AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
