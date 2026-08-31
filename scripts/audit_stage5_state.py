#!/usr/bin/env python3
"""Read-only audit for persisted perspective comparison state."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.perspective_state import find_comparison, upsert_comparison


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        first = {
            "comparison_id": "cmp-1",
            "proposition_ids": ["p2", "p1"],
            "source_ids": ["s2", "s1"],
            "comparison": {"relationship": "appears_to_contradict", "confidence": 0.8},
        }
        second = {
            "comparison_id": "cmp-1",
            "proposition_ids": ["p1", "p2"],
            "source_ids": ["s1", "s2", "s3"],
            "comparison": {"relationship": "different_framework", "confidence": 0.9},
        }
        history = upsert_comparison([], first, max_records=2)
        history = upsert_comparison(history, second, max_records=2)
        _assert(len(history) == 1, "Duplicate comparison ID was not replaced.")
        record = find_comparison(history, "cmp-1")
        _assert(record is not None, "Stored comparison could not be found.")
        _assert(record["proposition_ids"] == ["p1", "p2"], "Proposition IDs were not normalized.")
        _assert(record["source_ids"] == ["s1", "s2", "s3"], "Source provenance was lost.")
        _assert(record["comparison"]["relationship"] == "different_framework", "Latest comparison was not retained.")
        print("Stage 5 perspective-state runtime audit")
        print("========================================")
        print("PASS: bounded upsert, pair normalization, and provenance retention passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 5 STATE AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
