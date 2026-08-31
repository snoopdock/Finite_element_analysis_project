#!/usr/bin/env python3
"""Read-only audit for the explicit Stage 7 relationship-promotion gate."""

from __future__ import annotations

from core.relationship_promotion import promote_candidate

P1 = "11111111-1111-4111-8111-111111111111"
P2 = "22222222-2222-4222-8222-222222222222"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def state():
    return {
        "knowledge_graph": {
            "concepts": {
                P1: {"concept_id": P1, "name": "A", "type": "method"},
                P2: {"concept_id": P2, "name": "B", "type": "method"},
            },
            "propositions": {},
            "relationships": {},
            "relationship_candidates": {
                f"{P1}|{P2}|generalizes": {
                    "candidate_id": f"{P1}|{P2}|generalizes",
                    "source_id": P1,
                    "target_id": P2,
                    "type": "generalizes",
                    "source_ids": ["hint-source"],
                    "status": "candidate",
                }
            },
        }
    }


def main() -> int:
    try:
        s = state()
        cid = f"{P1}|{P2}|generalizes"

        check(promote_candidate(s, cid, {"status": "candidate", "type": "generalizes", "source_ids": ["source-x"]}) is None,
              "Unverified candidate was promoted.")
        check(promote_candidate(s, cid, {"status": "verified", "type": "related_to", "source_ids": ["source-x"]}) is None,
              "Wrong relationship type was promoted.")
        check(promote_candidate(s, cid, {"status": "verified", "type": "generalizes"}) is None,
              "Candidate without provenance was promoted.")
        check(not s["knowledge_graph"]["relationships"], "Rejected candidates altered authoritative relationships.")

        relationship_id = promote_candidate(s, cid, {
            "status": "verified",
            "type": "generalizes",
            "source_ids": ["source-x"],
            "confidence": 0.91,
            "reason": "The source explicitly defines A as a general framework for B.",
        })
        check(relationship_id, "Verified candidate was not promoted.")
        check(len(s["knowledge_graph"]["relationships"]) == 1, "Expected one authoritative relationship.")
        relationship = next(iter(s["knowledge_graph"]["relationships"].values()))
        check(relationship["type"] == "generalizes", "Promoted relationship type changed.")
        check(relationship["source_ids"] == ["source-x"], "Promotion provenance was not retained.")
        check(s["knowledge_graph"]["relationship_candidates"][cid]["status"] == "promoted",
              "Candidate status was not updated.")

        print("Stage 7 relationship promotion audit")
        print("=====================================")
        print("PASS: verification gate, provenance requirement, type matching, and promotion persistence passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 7 PROMOTION AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
