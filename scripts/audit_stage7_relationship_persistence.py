#!/usr/bin/env python3
"""Read-only audit for Stage 7 semantic relationship persistence."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.concept_relationship_service import analyze_candidate_concepts

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
P = "33333333-3333-4333-8333-333333333333"


class StubProvider:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = 0

    def budget_exhausted(self) -> bool:
        return False

    def chat(self, *args, **kwargs):
        self.calls += 1
        return self.response, None


class StubParser:
    def parse(self, text: str, model_name: str = ""):
        return json.loads(text)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        state = {
            "knowledge_graph": {
                "concepts": {
                    A: {"concept_id": A, "name": "FEM"},
                    B: {"concept_id": B, "name": "Galerkin"},
                },
                "propositions": {
                    P: {
                        "proposition_id": P,
                        "concept_ids": [A, B],
                        "statement": "Galerkin formulation is used within FEM.",
                        "source_ids": ["source-a", "source-b"],
                        "context": {"framework": "variational formulation"},
                    }
                },
                "relationships": {},
                "relationship_candidates": {},
            }
        }
        provider = StubProvider(json.dumps({
            "relationship": "complementary",
            "confidence": 0.88,
            "reason": "The source-backed proposition connects the concepts as complementary methods.",
            "source_ids": ["source-a"],
        }))
        result = analyze_candidate_concepts(state, provider, StubParser(), max_pairs=1, max_records=20)
        check(result["analyzed"] == 1, "Expected one semantic analysis.")
        check(result["recorded"] == 1, "Semantic proposal was not persisted.")
        candidates = state["knowledge_graph"]["relationship_candidates"]
        check(len(candidates) == 1, "Expected one relationship candidate.")
        candidate = next(iter(candidates.values()))
        check(candidate["type"] == "complements", "Persisted relationship type was not normalized.")
        check(candidate["proposition_ids"] == [P], "Supporting proposition provenance was not retained.")
        check(candidate["source_ids"] == ["source-a", "source-b"], "Source provenance was not retained.")
        check(candidate["status"] == "candidate", "Semantic proposal became authoritative.")
        check(not state["knowledge_graph"]["relationships"], "Semantic analysis created an authoritative relationship unexpectedly.")

        second = analyze_candidate_concepts(state, provider, StubParser(), max_pairs=1, max_records=20)
        check(second["recorded"] == 1, "Repeat analysis was not persisted deterministically.")
        check(len(state["knowledge_graph"]["relationship_candidates"]) == 1, "Repeat analysis duplicated the proposal.")

        print("Stage 7 relationship persistence audit")
        print("=======================================")
        print("PASS: semantic analysis, proposal persistence, provenance retention, repeat stability, and non-authoritative storage passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 7 RELATIONSHIP PERSISTENCE AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
