#!/usr/bin/env python3
"""Read-only audit for the Stage 7 verification-to-promotion adapter."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.concept_relationship_promotion_adapter import (
    promote_verified_result,
    verification_to_promotion_record,
)

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
CANDIDATE = f"{A}|{B}|generalizes"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def make_state():
    return {
        "knowledge_graph": {
            "concepts": {
                A: {"concept_id": A, "name": "A", "type": "method"},
                B: {"concept_id": B, "name": "B", "type": "method"},
            },
            "propositions": {},
            "relationships": {},
            "relationship_candidates": {
                CANDIDATE: {
                    "candidate_id": CANDIDATE,
                    "source_id": A,
                    "target_id": B,
                    "type": "generalizes",
                    "source_ids": ["source-a"],
                    "status": "candidate",
                }
            },
        }
    }


def result(decision: str, confidence: float = 0.91):
    return {
        "candidate_id": CANDIDATE,
        "expected_type": "generalizes",
        "verification": {
            "decision": decision,
            "confidence": confidence,
            "reason": "Evidence-backed verification result.",
            "source_ids": ["source-a"],
        },
    }


def main() -> int:
    try:
        normalized = verification_to_promotion_record(result("verified"))
        check(normalized["status"] == "verified", "Verified status was not preserved.")
        check(normalized["type"] == "generalizes", "Expected relationship type was lost.")
        check(normalized["source_ids"] == ["source-a"], "Verification provenance was lost.")

        state = make_state()
        check(promote_verified_result(state, result("rejected")) is None, "Rejected result was promoted.")
        check(promote_verified_result(state, result("insufficient_evidence")) is None, "Insufficient evidence was promoted.")
        check(not state["knowledge_graph"]["relationships"], "Non-verified result changed graph relationships.")

        relationship_id = promote_verified_result(state, result("verified"))
        check(relationship_id, "Verified result did not reach the promotion gate.")
        check(len(state["knowledge_graph"]["relationships"]) == 1, "Unexpected relationship count after promotion.")
        relationship = next(iter(state["knowledge_graph"]["relationships"].values()))
        check(relationship["type"] == "generalizes", "Promoted relationship type changed.")
        check(relationship["source_ids"] == ["source-a"], "Promoted relationship provenance changed.")

        print("Stage 7 promotion adapter audit")
        print("================================")
        print("PASS: verified-only adaptation, rejection safety, provenance, and delegation to the promotion gate passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 7 PROMOTION ADAPTER AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
