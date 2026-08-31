#!/usr/bin/env python3
"""Read-only audit for the Stage 5 perspective comparison ledger."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.perspective_ledger import record_comparison


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        state = {}
        skipped = {
            "comparison_id": "cmp-skip",
            "skipped": True,
            "comparison": {"relationship": "appears_to_contradict"},
        }
        record_comparison(state, skipped, max_records=5)
        _assert("perspective_comparisons" not in state, "Skipped comparison was persisted.")

        good = {
            "comparison_id": "cmp-1",
            "proposition_ids": ["p2", "p1"],
            "source_ids": ["s2", "s1"],
            "comparison": {"relationship": "different_framework", "confidence": 0.8},
        }
        record_comparison(state, good, max_records=5)
        _assert(len(state["perspective_comparisons"]) == 1, "Valid comparison was not persisted.")
        _assert(state["perspective_comparisons"][0]["proposition_ids"] == ["p1", "p2"], "Proposition IDs were not normalized.")
        _assert(state["perspective_comparisons"][0]["source_ids"] == ["s1", "s2"], "Source provenance was not normalized.")

        print("Stage 5 ledger runtime audit")
        print("============================")
        print("PASS: skipped comparisons are excluded and valid comparisons persist with normalized provenance.")
        return 0
    except Exception as exc:
        print(f"STAGE 5 LEDGER AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
