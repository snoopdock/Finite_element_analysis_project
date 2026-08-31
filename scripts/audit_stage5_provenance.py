#!/usr/bin/env python3
"""Read-only audit for Stage 5 comparison provenance."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.perspective_analyzer import _comparison_id


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        a = {
            "proposition_id": "p1",
            "source_ids": ["source-a"],
            "context": {"framework": "F1"},
        }
        b = {
            "proposition_id": "p2",
            "source_ids": ["source-b", "source-c"],
            "context": {"framework": "F2"},
        }
        _assert(_comparison_id(a, b) == _comparison_id(b, a), "Comparison identity is order-dependent.")
        _assert(_comparison_id(a, b) != _comparison_id(a, {**b, "proposition_id": "p3"}), "Distinct proposition pairs share an identity.")
        print("Stage 5 provenance runtime audit")
        print("================================")
        print("PASS: pair identity is symmetric and proposition-specific.")
        return 0
    except Exception as exc:
        print(f"STAGE 5 PROVENANCE AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
