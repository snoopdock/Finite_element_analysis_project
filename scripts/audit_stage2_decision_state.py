#!/usr/bin/env python3
"""Runtime audit for the Stage 2 decision ledger."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.decision_state import append_decision_history, decision_fingerprint, normalize_decision


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        record = {
            "section_id": "section-1",
            "title": "Example",
            "eta": 1.4,
            "priority": -3,
            "selected": 1,
            "model_index": 0,
            "model": "model-a",
        }
        normalized = normalize_decision(record)
        _assert(normalized["eta"] == 1.0, "Eta was not bounded.")
        _assert(normalized["priority"] == 0.0, "Priority was not made non-negative.")
        _assert(normalized["selected"] is True, "Selection was not normalized to bool.")
        _assert(normalized["fingerprint"] == decision_fingerprint({k: v for k, v in normalized.items() if k != "fingerprint"}), "Fingerprint is not stable.")

        state = {}
        append_decision_history(state, [record] * 5, max_records=3)
        _assert(len(state["decision_history"]) == 3, "Decision ledger exceeded its configured bound.")
        _assert(all("fingerprint" in item for item in state["decision_history"]), "A decision is missing its fingerprint.")

        append_decision_history(state, [], max_records=0)
        _assert(state["decision_history"] == [], "Zero-sized ledger bound did not clear history.")

        print("Stage 2 decision-state runtime audit")
        print("====================================")
        print("PASS: normalization, deterministic fingerprints, and bounded history passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 2 DECISION AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
