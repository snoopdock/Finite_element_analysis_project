#!/usr/bin/env python3
"""Read-only Stage 5 audit for graph-native perspective comparison."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.perspective_service import compare_graph_propositions


class _Provider:
    def __init__(self):
        self.calls = 0

    def budget_exhausted(self):
        return False

    def chat(self, messages, temperature, max_tokens, model=None):
        self.calls += 1
        return json.dumps({
            "relationship": "different_framework",
            "confidence": 0.82,
            "shared_context": ["finite elements"],
            "different_context": ["framework A", "framework B"],
            "reason": "The propositions use different frameworks.",
        }), None


class _Parser:
    def parse(self, text, model_name=None):
        return json.loads(text)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        state = {
            "knowledge_graph": {
                "concepts": {},
                "propositions": {
                    "p1": {
                        "proposition_id": "p1",
                        "statement": "Method A is stable",
                        "source_ids": ["source-a"],
                        "context": {"framework": "framework A"},
                    },
                    "p2": {
                        "proposition_id": "p2",
                        "statement": "Method A is unstable",
                        "source_ids": ["source-b"],
                        "context": {"framework": "framework B"},
                    },
                },
                "relationships": {},
                "concept_history": [],
            }
        }
        provider = _Provider()
        parser = _Parser()
        result = compare_graph_propositions(
            state,
            provider,
            parser,
            max_pairs=1,
            minimum_overlap=0.1,
            max_records=5,
        )
        _assert(result["candidates"] == 1, "Candidate count mismatch.")
        _assert(result["compared"] == 1, "Comparison count mismatch.")
        _assert(provider.calls == 1, "Pair cap did not bound LLM calls.")
        record = result["records"][0]
        _assert(set(record["proposition_ids"]) == {"p1", "p2"}, "Existing proposition identities were not preserved.")
        _assert(record["source_ids"] == ["source-a", "source-b"], "Comparison provenance was lost.")
        _assert(len(state.get("perspective_comparisons", [])) == 1, "Comparison was not persisted.")
        _assert(state["perspective_comparisons"][0]["comparison"]["relationship"] == "different_framework", "Relationship was not persisted.")

        print("Stage 5 perspective service audit")
        print("=================================")
        print("PASS: graph propositions, provenance, pair bounds, and persistence passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 5 SERVICE AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
