#!/usr/bin/env python3
"""Read-only runtime audit for scientific perspective comparisons.

Run from the repository root:
    python scripts/audit_stage5_comparison.py

No LLM or network calls are made.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.perspective_analyzer import _comparison_id, normalize_comparison


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        a = {
            "proposition_id": "00000000-0000-0000-0000-000000000001",
            "statement": "Method A is stable.",
            "source_ids": ["paper-a"],
            "context": {"framework": "F1", "assumptions": ["small deformation"]},
        }
        b = {
            "proposition_id": "00000000-0000-0000-0000-000000000002",
            "statement": "Method A is unstable.",
            "source_ids": ["paper-b"],
            "context": {"framework": "F2", "assumptions": ["large deformation"]},
        }
        _assert(_comparison_id(a, b) == _comparison_id(b, a), "Comparison ID depends on proposition order.")

        normalized = normalize_comparison({
            "relationship": "different_framework",
            "confidence": 1.5,
            "shared_context": [" F1 ", "F1"],
            "different_context": "F2",
        })
        _assert(normalized["relationship"] == "different_framework", "Relationship normalization failed.")
        _assert(normalized["confidence"] == 1.0, "Confidence was not bounded.")
        _assert(normalized["shared_context"] == ["F1"], "Context list was not normalized.")
        _assert(normalized["different_context"] == ["F2"], "Scalar context was not normalized.")

        print("Stage 5 comparison runtime audit")
        print("================================")
        print("PASS: comparison identity, relationship normalization, confidence bounds, and context normalization passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 5 COMPARISON AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
