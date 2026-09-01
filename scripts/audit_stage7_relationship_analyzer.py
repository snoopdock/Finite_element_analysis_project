#!/usr/bin/env python3
"""Read-only audit for the Stage 7 semantic concept-relationship analyzer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.concept_relationship_analyzer import (
    analyze_concept_relationship,
    normalize_relationship_proposal,
)

P1 = "11111111-1111-4111-8111-111111111111"
P2 = "22222222-2222-4222-8222-222222222222"
S1 = "source-a"
S2 = "source-b"


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
        concept_a = {"concept_id": P1, "name": "Finite Element Method", "type": "method"}
        concept_b = {"concept_id": P2, "name": "Galerkin Method", "type": "method"}
        propositions = [{
            "proposition_id": "33333333-3333-4333-8333-333333333333",
            "statement": "Galerkin formulation is used within the finite element method.",
            "source_ids": [S1, S2],
            "context": {"framework": "variational formulation", "assumptions": ["small deformation"]},
        }]

        provider = StubProvider(json.dumps({
            "relationship": "complementary",
            "confidence": 0.91,
            "reason": "The supplied propositions support use of Galerkin formulation within FEM.",
            "source_ids": [S1],
        }))
        result = analyze_concept_relationship(
            concept_a, concept_b, propositions, provider, StubParser()
        )
        proposal = result["proposal"]
        check(not result["skipped"], "Valid relationship analysis was skipped.")
        check(proposal["relationship"] == "complements", "Unexpected relationship normalization.")
        check(proposal["confidence"] == 0.91, "Confidence normalization failed.")
        check(proposal["source_ids"] == [S1, S2], "Provenance union was not preserved.")
        check(provider.calls == 1, "Expected exactly one bounded LLM call.")

        insufficient = analyze_concept_relationship(
            concept_a, concept_b, [], provider, StubParser()
        )
        check(insufficient["skipped"], "Missing evidence was not rejected.")

        exhausted_provider = StubProvider("{}", exhausted=True)
        exhausted = analyze_concept_relationship(
            concept_a, concept_b, propositions, exhausted_provider, StubParser()
        )
        check(exhausted["skipped"], "Budget exhaustion was not respected.")
        check(exhausted_provider.calls == 0, "Budget exhaustion still triggered a model call.")

        malformed = normalize_relationship_proposal({
            "relationship": "invented_relationship",
            "confidence": 9,
            "source_ids": "source-x",
        })
        check(malformed["relationship"] == "insufficient_evidence", "Unsupported relation was accepted.")
        check(malformed["confidence"] == 1.0, "Confidence was not bounded.")
        check(malformed["source_ids"] == ["source-x"], "Opaque provenance normalization failed.")

        missing_identity = analyze_concept_relationship(
            {"name": "A"}, concept_b, propositions, provider, StubParser()
        )
        check(missing_identity["skipped"], "Missing concept identity was not rejected.")

        print("Stage 7 semantic relationship analyzer audit")
        print("=============================================")
        print("PASS: provenance, normalization, evidence requirement, identity validation, and budget checks passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 7 RELATIONSHIP ANALYZER AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
