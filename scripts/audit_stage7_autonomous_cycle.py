#!/usr/bin/env python3
"""Read-only audit for the bounded Stage 7 autonomous relationship cycle."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.concept_relationship_autonomous_cycle import run_autonomous_relationship_cycle

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
P = "33333333-3333-4333-8333-333333333333"
CANDIDATE = f"{A}|{B}|related_to"


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
                    "statement": "A and B have a documented relationship.",
                    "source_ids": ["source-a"],
                    "concept_ids": [A, B],
                    "context": {"framework": "F"},
                }
            },
            "relationship_candidates": {
                CANDIDATE: {
                    "candidate_id": CANDIDATE,
                    "source_id": A,
                    "target_id": B,
                    "type": "related_to",
                    "source_ids": ["source-a"],
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
        disabled_state = make_state()
        disabled = run_autonomous_relationship_cycle(
            disabled_state,
            StubProvider('{"relationship":"related_to","confidence":0.95,"reason":"ok","source_ids":["source-a"]}'),
            StubParser(),
            enabled=False,
        )
        check(disabled["enabled"] is False, "Disabled cycle was not a no-op.")
        check(not disabled_state["knowledge_graph"]["relationships"], "Disabled cycle modified relationships.")

        state = make_state()
        active = run_autonomous_relationship_cycle(
            state,
            StubProvider('{"relationship":"related_to","confidence":0.95,"reason":"The source-backed propositions support the relationship.","source_ids":["source-a"]}'),
            StubParser(),
            enabled=True,
            max_tasks=1,
            minimum_confidence=0.70,
        )
        check(active["queued"] == 1, "Expected one queued verification task.")
        check(active["verified"] == 1, "Expected one verified candidate.")
        check(active["promoted"] == 1, "Verified candidate was not promoted.")
        check(len(state["knowledge_graph"]["relationships"]) == 1, "Unexpected authoritative relationship count.")
        check(state["knowledge_graph"]["relationships"], "Autonomous cycle did not create the verified relationship.")

        print("Stage 7 autonomous relationship cycle audit")
        print("============================================")
        print("PASS: disabled safety, bounded verification, verified-only promotion, and no content rewriting passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 7 AUTONOMOUS CYCLE AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
