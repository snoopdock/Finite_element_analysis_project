#!/usr/bin/env python3
"""Read-only audit for the isolated Stage 7 relationship cycle boundary."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.concept_relationship_cycle import run_stage7_relationship_cycle

P1 = "11111111-1111-4111-8111-111111111111"
P2 = "22222222-2222-4222-8222-222222222222"
S1 = "source-a"
S2 = "source-b"


class StubProvider:
    def __init__(self):
        self.calls = 0

    def budget_exhausted(self) -> bool:
        return False

    def chat(self, *args, **kwargs):
        self.calls += 1
        return (
            '{"relationship":"complements","confidence":0.9,'
            '"reason":"Both source-backed propositions describe complementary methods.",'
            '"source_ids":["source-a","source-b"]}',
            None,
        )


class StubParser:
    def parse(self, text, model_name=None):
        import json
        return json.loads(text)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        state = {
            "knowledge_graph": {
                "concepts": {
                    P1: {"concept_id": P1, "name": "Method A", "type": "method"},
                    P2: {"concept_id": P2, "name": "Method B", "type": "method"},
                },
                "propositions": {
                    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa": {
                        "proposition_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                        "statement": "Method A addresses regime X.",
                        "concept_ids": [P1, P2],
                        "source_ids": [S1],
                        "context": {},
                    },
                    "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb": {
                        "proposition_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                        "statement": "Method B addresses regime Y.",
                        "concept_ids": [P1, P2],
                        "source_ids": [S2],
                        "context": {},
                    },
                },
                "relationships": {},
                "relationship_candidates": {},
            }
        }
        provider = StubProvider()
        parser = StubParser()

        disabled = run_stage7_relationship_cycle(
            state,
            provider,
            parser,
            {"semantic_verification": {"concept_relationship_enabled": False}},
        )
        check(disabled["enabled"] is False, "Disabled cycle did not no-op.")
        check(provider.calls == 0, "Disabled cycle consumed an LLM call.")

        enabled = run_stage7_relationship_cycle(
            state,
            provider,
            parser,
            {"semantic_verification": {
                "concept_relationship_enabled": True,
                "max_concept_relationship_pairs_per_cycle": 1,
                "max_concept_relationship_propositions_per_pair": 4,
                "concept_relationship_max_records": 4,
                "concept_relationship_max_tokens": 650,
            }},
        )
        check(enabled["enabled"] is True, "Enabled cycle was not marked enabled.")
        check(enabled["analyzed"] == 1, "Expected one bounded concept analysis.")
        check(provider.calls == 1, "Expected exactly one LLM call.")
        check("last_stage7_relationship_cycle" in state, "Cycle trace was not persisted.")
        check("relationship_candidates" in state["knowledge_graph"], "Candidate collection missing.")
        check(not state["knowledge_graph"]["relationships"], "Cycle promoted a relationship unexpectedly.")
        check(state["knowledge_graph"]["relationship_candidates"], "Semantic proposal was not persisted as candidate.")

        print("Stage 7 relationship cycle audit")
        print("================================")
        print("PASS: disabled no-op, bounded execution, state trace, candidate persistence, and no implicit promotion passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 7 CYCLE AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
