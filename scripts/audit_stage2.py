#!/usr/bin/env python3
"""Read-only Stage 2 runtime smoke audit.

Run from the repository root:
    python scripts/audit_stage2.py

Uses in-memory stubs and never calls an LLM or writes project state.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.oaa_policy import OAAActionPolicy
from analysis.policy_oaa_loop import PolicyAwareOAALoop
from analysis.writing_policy import WritingDecisionPolicy
from core.decision_state import append_decision_history


class _Indicator:
    def compute(self, section_or_topic, history):
        return float(section_or_topic.get("eta", 0.0)) if isinstance(section_or_topic, dict) else 0.0


class _Splitter:
    def is_too_simple(self, section, knowledge_base):
        return False


class _Merger:
    def find_merge_candidates(self, sections):
        return []

    def should_merge(self, sections, overlap):
        return False


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        models = ["strong", "standard", "economy"]
        sections = [
            {"section_id": "s1", "title": "A", "eta": 0.9},
            {"section_id": "s2", "title": "B", "eta": 0.4},
        ]
        decisions = WritingDecisionPolicy(theta=0.75, tau=0.60).decide(
            sections,
            _Indicator(),
            {},
            models,
        )
        _assert(len(decisions) == 2, "Writer decision count mismatch.")
        records = [decision.to_dict(models) for decision in decisions]
        _assert(all(record["model"] == models[record["model_index"]] for record in records), "Writer model decision is inconsistent.")

        state = {}
        append_decision_history(state, records, max_records=2)
        _assert(len(state["decision_history"]) == 2, "Decision ledger bound failed.")

        oaa = OAAActionPolicy()
        anomalies = [
            {"key": "a", "type": "repetition", "action": "deduplicate", "section_id": "s1"},
            {"key": "b", "type": "too_simple", "action": "split_section", "section_id": "s2"},
        ]
        chosen = oaa.choose(anomalies, {"a": 0, "b": 4})
        ranked = oaa.rank(anomalies, {"a": 0, "b": 4})
        _assert(chosen is not None, "OAA returned no decision.")
        _assert(chosen.key == ranked[0]["key"], "OAA choose/rank mismatch.")

        config = {
            "oaa": {"severity_weights": {"repetition": 0.41}},
        }
        loop = PolicyAwareOAALoop(config, _Splitter(), _Merger())
        _assert(abs(loop.action_policy.severity_weights["repetition"] - 0.41) < 1e-12, "Top-level OAA configuration was not applied.")

        print("Stage 2 combined runtime smoke audit")
        print("====================================")
        print("PASS: writer decisions, decision ledger, OAA selection, and configuration flow passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 2 AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
