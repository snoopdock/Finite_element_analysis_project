#!/usr/bin/env python3
"""Runtime audit for the Stage 2 writing decision policy.

Run from the repository root:
    python scripts/audit_stage2_policy.py

Uses in-memory stubs only; it never calls an LLM or writes project state.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.writing_policy import SectionDecision, WritingDecisionPolicy


class _Indicator:
    def compute(self, section_or_topic, history):
        if isinstance(section_or_topic, dict):
            return float(section_or_topic.get("eta", 0.0))
        return 0.0


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        indicator = _Indicator()
        policy = WritingDecisionPolicy(theta=0.75, tau=0.60)
        sections = [
            {"section_id": "s1", "title": "A", "eta": 0.9},
            {"section_id": "s2", "title": "B", "eta": 0.5},
            {
                "section_id": "s3",
                "title": "C",
                "eta": 0.7,
                "semantic_feedback": {
                    "action": "analyze_perspectives",
                    "confidence": 1.0,
                },
            },
        ]
        decisions = policy.decide(sections, indicator, {}, ["strong", "standard", "economy"])

        _assert(len(decisions) == 3, "Unexpected decision count.")
        _assert(all(isinstance(item, SectionDecision) for item in decisions), "Decision type mismatch.")
        _assert(all(0.0 <= item.eta <= 1.0 for item in decisions), "Eta left [0,1].")
        _assert(all(item.priority >= 0.0 for item in decisions), "Negative priority detected.")
        _assert(sum(item.selected for item in decisions) >= 1, "No section selected.")
        _assert(any(item.section_id == "s3" and item.priority > item.eta for item in decisions), "Semantic priority was not applied.")
        _assert(all(item.model in {"strong", "standard", "economy"} for item in decisions), "Unknown model selected.")

        print("Stage 2 policy runtime audit")
        print("============================")
        print(f"decisions: {len(decisions)}")
        print(f"selected: {sum(item.selected for item in decisions)}")
        print("PASS: priority, selection, semantic feedback, and model-selection invariants passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 2 POLICY AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
