#!/usr/bin/env python3
"""Read-only final Stage 5 audit.

Run from the repository root:
    python scripts/audit_stage5_final.py

Uses in-memory records and stubbed responses. No external services are called.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.perspective_analyzer import _comparison_id, compare_propositions
from analysis.perspective_candidates import candidate_pairs
from analysis.perspective_service import compare_graph_propositions
from core.perspective_state import upsert_comparison


class StubProvider:
    def __init__(self):
        self.calls = 0
        self.exhausted = False

    def budget_exhausted(self):
        return self.exhausted

    def chat(self, messages, temperature, max_tokens, model=None):
        self.calls += 1
        return json.dumps({
            "relationship": "different_framework",
            "confidence": 0.84,
            "shared_context": ["finite element analysis"],
            "different_context": ["framework A", "framework B"],
            "reason": "The propositions differ in framework.",
        }), None


class StubParser:
    def parse(self, text, model_name=None):
        return json.loads(text)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        a = {
            "proposition_id": "p1",
            "statement": "Method A is stable",
            "source_ids": ["source-a"],
            "context": {"framework": "F1", "assumptions": ["A"]},
        }
        b = {
            "proposition_id": "p2",
            "statement": "Method A is unstable",
            "source_ids": ["source-b"],
            "context": {"framework": "F2", "assumptions": ["B"]},
        }
        c = {
            "proposition_id": "p3",
            "statement": "Method A is stable",
            "source_ids": ["source-a"],
            "context": {"framework": "F1"},
        }

        check(_comparison_id(a, b) == _comparison_id(b, a), "Comparison identity is not symmetric.")

        pairs = candidate_pairs([a, b, c], max_pairs=8, minimum_overlap=0.15)
        ids = {tuple(sorted((x["proposition_id"], y["proposition_id"]))) for x, y in pairs}
        check(("p1", "p2") in ids, "Cross-source pair missing.")
        check(("p1", "p3") not in ids, "Same-source pair was selected.")

        provider = StubProvider()
        parser = StubParser()
        comparison = compare_propositions(a, b, provider, parser)
        check(not comparison["skipped"], "Valid comparison was skipped.")
        check(set(comparison["proposition_ids"]) == {"p1", "p2"}, "Proposition IDs were lost.")
        check(comparison["source_ids"] == ["source-a", "source-b"], "Source provenance was lost.")

        history = upsert_comparison([], comparison, max_records=2)
        history = upsert_comparison(history, comparison, max_records=2)
        check(len(history) == 1, "Duplicate comparison was not collapsed.")

        graph_state = {
            "knowledge_graph": {
                "concepts": {},
                "propositions": {"p1": a, "p2": b},
                "relationships": {},
                "concept_history": [],
            }
        }
        service_provider = StubProvider()
        service_result = compare_graph_propositions(
            graph_state,
            service_provider,
            parser,
            max_pairs=1,
            minimum_overlap=0.15,
            max_records=4,
        )
        check(service_result["candidates"] == 1, "Service candidate bound failed.")
        check(service_result["compared"] == 1, "Service comparison count failed.")
        check(service_provider.calls == 1, "Service exceeded comparison call bound.")
        check(len(graph_state["perspective_comparisons"]) == 1, "Service did not persist comparison.")
        check(
            set(graph_state["perspective_comparisons"][0]["proposition_ids"]) == {"p1", "p2"},
            "Service did not preserve graph proposition identities.",
        )

        failed = compare_propositions(a, b, StubProvider(), parser)
        check(not failed["skipped"], "Stub failure scenario unexpectedly skipped.")

        exhausted = StubProvider()
        exhausted.exhausted = True
        skipped = compare_propositions(a, b, exhausted, parser)
        check(skipped["skipped"], "Budget exhaustion was not contained.")

        print("Stage 5 final runtime audit")
        print("===========================")
        print("PASS: comparison identity, context/provenance, candidate selection, bounded service execution, persistence, and budget containment passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 5 FINAL AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
