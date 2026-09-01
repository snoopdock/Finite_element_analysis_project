#!/usr/bin/env python3
"""Read-only audit for the bounded Stage 7 concept-relationship service."""

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
C = "33333333-3333-4333-8333-333333333333"
P1 = "44444444-4444-4444-8444-444444444444"
P2 = "55555555-5555-4555-8555-555555555555"


class StubProvider:
    def __init__(self, response: str, exhausted: bool = False) -> None:
        self.response = response
        self.exhausted = exhausted
        self.calls = 0

    def budget_exhausted(self) -> bool:
        return self.exhausted

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
                    A: {"concept_id": A, "name": "Finite Element Method", "type": "method"},
                    B: {"concept_id": B, "name": "Galerkin Method", "type": "method"},
                    C: {"concept_id": C, "name": "Mesh", "type": "concept"},
                },
                "propositions": {
                    P1: {
                        "proposition_id": P1,
                        "concept_ids": [A, B],
                        "statement": "Galerkin formulation is used within FEM.",
                        "source_ids": ["source-a", "source-b"],
                        "context": {"framework": "variational formulation"},
                    },
                    P2: {
                        "proposition_id": P2,
                        "concept_ids": [A, C],
                        "statement": "FEM uses a mesh to discretize a domain.",
                        "source_ids": ["source-c"],
                        "context": {},
                    },
                },
                "relationships": {},
            }
        }

        provider = StubProvider(json.dumps({
            "relationship": "complementary",
            "confidence": 0.86,
            "reason": "Both concepts occur together in source-backed propositions without a hierarchy being established.",
            "source_ids": ["source-a"],
        }))
        result = analyze_candidate_concepts(
            state,
            provider,
            StubParser(),
            max_pairs=1,
            max_propositions_per_pair=2,
        )
        check(result["candidates"] == 1, "Pair bound was not applied.")
        check(result["analyzed"] == 1, "Candidate pair was not analyzed.")
        check(provider.calls == 1, "Expected one bounded LLM call.")
        check(result["records"][0]["proposal"]["relationship"] == "complements", "Proposal normalization failed.")
        check(not state["knowledge_graph"]["relationships"], "Analyzer/service created an authoritative relationship unexpectedly.")

        exhausted = StubProvider("{}", exhausted=True)
        result_exhausted = analyze_candidate_concepts(state, exhausted, StubParser(), max_pairs=1)
        check(result_exhausted["analyzed"] == 0, "Budget exhaustion did not stop analysis.")
        check(exhausted.calls == 0, "Budget exhaustion triggered a model call.")

        print("Stage 7 concept relationship service audit")
        print("==========================================")
        print("PASS: bounded pairing, source-backed proposition filtering, proposal-only output, and budget stopping passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 7 RELATIONSHIP SERVICE AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
