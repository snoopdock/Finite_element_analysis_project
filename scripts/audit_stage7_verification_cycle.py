#!/usr/bin/env python3
"""Read-only audit for the bounded Stage 7 verification cycle."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.concept_relationship_verification_cycle import run_verification_cycle

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
P = "33333333-3333-4333-8333-333333333333"
S = "source-a"


class StubProvider:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def budget_exhausted(self):
        return False

    def chat(self, messages, temperature=0.0, max_tokens=650, model=None):
        self.calls += 1
        return self.response, None


class StubParser:
    def parse(self, text, model_name=None):
        return json.loads(text)


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
            "propositions": {
                P: {
                    "proposition_id": P,
                    "statement": "A and B are related.",
                    "source_ids": [S],
                    "concept_ids": [A, B],
                    "context": {"framework": "F", "assumptions": ["X"]},
                }
            },
            "relationship_candidates": {
                f"{A}|{B}|related_to": {
                    "candidate_id": f"{A}|{B}|related_to",
                    "source_id": A,
                    "target_id": B,
                    "type": "related_to",
                    "source_ids": [S],
                    "proposition_ids": [P],
                    "confidence": 0.1,
                    "status": "candidate",
                }
            },
            "relationships": {},
        }
    }


def main() -> int:
    try:
        state = make_state()
        provider = StubProvider(
            '{"relationship":"related_to","confidence":0.92,"reason":"The evidence supports a meaningful relation.","source_ids":["source-a"]}'
        )
        result = run_verification_cycle(
            state,
            provider,
            StubParser(),
            max_tasks=1,
            minimum_confidence=0.70,
        )
        check(result["queued"] == 1, "Expected one queued task.")
        check(result["verified"] == 1, "Expected one verified candidate.")
        check(result["rejected"] == 0 and result["insufficient_evidence"] == 0, "Unexpected verification outcome.")
        check(provider.calls == 1, "Verification cycle exceeded expected provider calls.")
        check(not state["knowledge_graph"]["relationships"], "Verification cycle promoted a relationship unexpectedly.")
        check(state["last_concept_relationship_verification"]["verified"] == 1, "Verification summary was not persisted.")

        print("Stage 7 verification cycle audit")
        print("=================================")
        print("PASS: queue consumption, bounded execution, verification summary, and non-promotion passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 7 VERIFICATION CYCLE AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
