#!/usr/bin/env python3
"""Runtime audit for explicit OAA action decisions."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.oaa_policy import AdjustmentDecision, OAAActionPolicy


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        policy = OAAActionPolicy()
        anomalies = [
            {"key": "too-simple:s1", "type": "too_simple", "action": "split", "section_id": "s1"},
            {"key": "repetition:s2", "type": "repetition", "action": "review", "section_id": "s2"},
        ]
        decision = policy.choose(anomalies, {"too-simple:s1": 4, "repetition:s2": 1})
        _assert(isinstance(decision, AdjustmentDecision), "No typed OAA decision returned.")
        _assert(decision.key, "Decision key is empty.")
        _assert(decision.action == "split", "Highest-ranked anomaly was not selected.")
        record = decision.to_dict()
        _assert(record["score"]["score"] >= 0.0, "Decision score is negative.")
        _assert(0.0 <= record["score"]["severity"] <= 1.0, "Severity escaped bounds.")
        _assert(0.0 <= record["score"]["persistence"] <= 1.0, "Persistence escaped bounds.")
        _assert(0.0 <= record["score"]["cost"] <= 1.0, "Cost escaped bounds.")

        print("Stage 2 OAA decision runtime audit")
        print("==================================")
        print("PASS: typed selection, bounded score fields, and serialization passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 2 OAA DECISION AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
