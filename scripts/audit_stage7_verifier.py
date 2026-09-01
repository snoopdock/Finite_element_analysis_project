#!/usr/bin/env python3
"""Read-only audit for Stage 7 source-backed relationship verification."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.concept_relationship_verifier import normalize_verification, verify_candidate_relationship

P1 = "11111111-1111-4111-8111-111111111111"
P2 = "22222222-2222-4222-8222-222222222222"
S1 = "source-a"
PROP = "33333333-3333-4333-8333-333333333333"


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
        import json
        return json.loads(text)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def make_state():
    return {
        "knowledge_graph": {
            "concepts": {
                P1: {"concept_id": P1, "name": "A", "type": "method"},
                P2: {"concept_id": P2, "name": "B", "type": "method"},
            },
            "propositions": {
                PROP: {
                    "proposition_id": PROP,
                    "statement": "A and B are used together.",
                    "source_ids": [S1],
                    "concept_ids": [P1, P2],
                    "context": {"framework": "F", "assumptions": ["X"]},
                }
            },
            "relationships": {},
        }
    }


def run(response):
    state = make_state()
    task = {
        "candidate_id": f"{P1}|{P2}|related_to",
        "source_id": P1,
        "target_id": P2,
        "type": "related_to",
        "source_ids": [S1],
        "proposition_ids": [PROP],
    }
    result = verify_candidate_relationship(
        state,
        task,
        StubProvider(response),
        StubParser(),
        minimum_confidence=0.70,
    )
    return state, result


def main() -> int:
    try:
        supported_state, supported = run(
            '{"relationship":"related_to","confidence":0.92,"reason":"The supplied source links the concepts.","source_ids":["source-a"]}'
        )
        check(supported["verification"]["decision"] == "verified", "Supported candidate was not verified.")
        check(not supported_state["knowledge_graph"]["relationships"], "Verifier mutated authoritative relationships.")

        rejected_state, rejected = run(
            '{"relationship":"generalizes","confidence":0.91,"reason":"The evidence does not support the proposed relation.","source_ids":["source-a"]}'
        )
        check(rejected["verification"]["decision"] == "rejected", "Mismatched relationship was not rejected.")
        check(not rejected_state["knowledge_graph"]["relationships"], "Rejected verification mutated graph relationships.")

        uncertain_state, uncertain = run(
            '{"relationship":"related_to","confidence":0.40,"reason":"The source is not decisive.","source_ids":["source-a"]}'
        )
        check(uncertain["verification"]["decision"] == "insufficient_evidence", "Low-confidence verification was not classified as insufficient evidence.")
        check(not uncertain_state["knowledge_graph"]["relationships"], "Uncertain verification mutated graph relationships.")

        normalized = normalize_verification({"decision": "unknown", "confidence": "bad"})
        check(normalized["decision"] == "insufficient_evidence", "Invalid decision was not normalized safely.")
        check(normalized["confidence"] == 0.0, "Invalid confidence was not normalized safely.")

        print("Stage 7 relationship verifier audit")
        print("====================================")
        print("PASS: supported/rejected/insufficient decisions, provenance, normalization, and non-mutation passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 7 VERIFIER AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
