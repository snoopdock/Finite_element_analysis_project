#!/usr/bin/env python3
"""Read-only Stage 5 integration audit for the graph-native perspective path."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.perspective_registry import record_perspective_jobs


class _Provider:
    def __init__(self):
        self.calls = 0

    def budget_exhausted(self):
        return False

    def chat(self, messages, temperature, max_tokens, model=None):
        self.calls += 1
        return json.dumps({
            "relationship": "different_framework",
            "confidence": 0.9,
            "shared_context": ["Method A"],
            "different_context": ["F1", "F2"],
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
                        "context": {"framework": "F1"},
                    },
                    "p2": {
                        "proposition_id": "p2",
                        "statement": "Method A is unstable",
                        "source_ids": ["source-b"],
                        "context": {"framework": "F2"},
                    },
                },
                "relationships": {},
                "concept_history": [],
            }
        }
        provider = _Provider()
        parser = _Parser()
        result = record_perspective_jobs(
            state,
            [{"section_id": "section-1", "claim": "Method A"}],
            provider,
            parser,
            max_jobs=1,
        )

        _assert(result["jobs_checked"] == 1, "Compatibility adapter did not report comparison.")
        _assert(result["relationships_added"] == 1, "Graph relationship was not persisted.")
        _assert(provider.calls == 1, "Adapter exceeded the requested pair bound.")
        relationships = state["knowledge_graph"]["relationships"]
        _assert(len(relationships) == 1, "Unexpected relationship count.")
        relationship = next(iter(relationships.values()))
        _assert(set(relationship["proposition_ids"]) == {"p1", "p2"}, "Proposition identities changed at integration boundary.")
        _assert(set(relationship["source_ids"]) == {"source-a", "source-b"}, "Relationship provenance was lost.")
        _assert(relationship["type"] == "contrasts_with", "Relationship type was not mapped correctly.")

        print("Stage 5 integration audit")
        print("=========================")
        print("PASS: legacy API delegates to graph-native comparison without synthetic propositions.")
        return 0
    except Exception as exc:
        print(f"STAGE 5 INTEGRATION AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
