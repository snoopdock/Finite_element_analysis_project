#!/usr/bin/env python3
"""Read-only audit for Stage 7 relationship verification queueing."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.concept_relationship_queue import verification_queue

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
C = "33333333-3333-4333-8333-333333333333"
D = "44444444-4444-4444-8444-444444444444"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        state = {
            "knowledge_graph": {
                "relationship_candidates": {
                    "candidate-high": {
                        "candidate_id": "candidate-high",
                        "source_id": A,
                        "target_id": B,
                        "type": "related_to",
                        "confidence": 0.9,
                        "source_ids": ["s1"],
                        "status": "candidate",
                    },
                    "candidate-low": {
                        "candidate_id": "candidate-low",
                        "source_id": C,
                        "target_id": D,
                        "type": "complements",
                        "confidence": 0.2,
                        "source_ids": ["s2"],
                        "status": "candidate",
                    },
                    "promoted": {
                        "candidate_id": "promoted",
                        "source_id": A,
                        "target_id": C,
                        "type": "generalizes",
                        "confidence": 0.1,
                        "status": "promoted",
                    },
                    "malformed": {
                        "candidate_id": "malformed",
                        "source_id": "",
                        "target_id": D,
                        "type": "related_to",
                        "status": "candidate",
                    },
                }
            }
        }

        before = repr(state)
        tasks = verification_queue(state, max_tasks=8)
        check(len(tasks) == 2, "Unexpected verification-task count.")
        check(tasks[0]["candidate_id"] == "candidate-low", "Lowest-confidence candidate was not prioritized.")
        check(tasks[1]["candidate_id"] == "candidate-high", "Second candidate order is incorrect.")
        check(all(task["candidate_id"] != "promoted" for task in tasks), "Promoted candidate entered queue.")
        check(all(task["source_id"] and task["target_id"] and task["type"] for task in tasks), "Malformed candidate entered queue.")
        check(len(verification_queue(state, max_tasks=1)) == 1, "Task bound was not enforced.")
        check(repr(state) == before, "Queue mutated graph state.")

        print("Stage 7 relationship verification queue audit")
        print("==============================================")
        print("PASS: candidate filtering, confidence ordering, deterministic bounds, malformed-record exclusion, and read-only behavior passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 7 QUEUE AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
