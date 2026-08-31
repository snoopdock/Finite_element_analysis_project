#!/usr/bin/env python3
"""Read-only audit for targeted Stage 5 perspective jobs.

Run from the repository root:
    python scripts/audit_stage5_targeted.py

Uses in-memory graph data and stubbed LLM responses. No external services.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.perspective_registry import record_perspective_jobs


class StubProvider:
    def __init__(self):
        self.calls = 0
        self.seen_pairs = []
        self.exhausted = False

    def budget_exhausted(self):
        return self.exhausted

    def chat(self, messages, temperature, max_tokens, model=None):
        self.calls += 1
        content = messages[-1].get("content", "") if messages else ""
        self.seen_pairs.append(content)
        return json.dumps({
            "relationship": "different_framework",
            "confidence": 0.8,
            "shared_context": ["Method A"],
            "different_context": ["F1", "F2"],
            "reason": "The propositions use different frameworks.",
        }), None


class StubParser:
    def parse(self, text, model_name=None):
        return json.loads(text)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def make_state():
    def proposition(pid, statement, source, framework):
        return {
            "proposition_id": pid,
            "statement": statement,
            "source_ids": [source],
            "context": {"framework": framework},
        }

    return {
        "knowledge_graph": {
            "concepts": {},
            "propositions": {
                "11111111-1111-4111-8111-111111111111": proposition(
                    "11111111-1111-4111-8111-111111111111", "Method A is stable", "s1", "F1"
                ),
                "22222222-2222-4222-8222-222222222222": proposition(
                    "22222222-2222-4222-8222-222222222222", "Method A is unstable", "s2", "F2"
                ),
                "33333333-3333-4333-8333-333333333333": proposition(
                    "33333333-3333-4333-8333-333333333333", "Method B is stable", "s3", "F3"
                ),
                "44444444-4444-4444-8444-444444444444": proposition(
                    "44444444-4444-4444-8444-444444444444", "Method B is unstable", "s4", "F4"
                ),
            },
            "relationships": {},
            "concept_history": [],
        }
    }


def main() -> int:
    try:
        state = make_state()
        provider = StubProvider()
        parser = StubParser()
        p1 = "11111111-1111-4111-8111-111111111111"
        p2 = "22222222-2222-4222-8222-222222222222"
        p3 = "33333333-3333-4333-8333-333333333333"
        p4 = "44444444-4444-4444-8444-444444444444"
        jobs = [
            {"section_id": "sec-a", "proposition_ids": [p1, p2]},
            {"section_id": "sec-b", "proposition_ids": [p3, p4]},
        ]

        result = record_perspective_jobs(
            state,
            jobs,
            provider,
            parser,
            max_jobs=2,
        )

        check(result["jobs_checked"] == 2, "Not all bounded jobs were processed.")
        check(result["relationships_added"] == 2, "Expected one relationship per targeted job.")
        check(provider.calls == 2, "Targeted job processing exceeded the job bound.")

        pairs = [
            set(record.get("proposition_ids", []))
            for record in result["reports"]
            if isinstance(record, dict)
        ]
        check({p1, p2} in pairs, "First job did not target its proposition IDs.")
        check({p3, p4} in pairs, "Second job did not target its proposition IDs.")
        check({p1, p3} not in pairs, "A job compared unrelated propositions.")
        check({p2, p4} not in pairs, "A job compared unrelated propositions.")

        relationships = state["knowledge_graph"]["relationships"]
        endpoints = {
            tuple(sorted(rel["proposition_ids"]))
            for rel in relationships.values()
        }
        check(tuple(sorted((p1, p2))) in endpoints, "First targeted relationship missing.")
        check(tuple(sorted((p3, p4))) in endpoints, "Second targeted relationship missing.")

        print("Stage 5 targeted perspective audit")
        print("=================================")
        print("PASS: job-level targeting, UUID identity, bounds, proposition identity, and relationship endpoints passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 5 TARGETED AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
