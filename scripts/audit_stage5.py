#!/usr/bin/env python3
"""Read-only combined runtime audit for Stage 5.

Run from the repository root:
    python scripts/audit_stage5.py

No LLM calls or external services are used.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.perspective_analyzer import _comparison_id, normalize_comparison
from analysis.perspective_candidates import candidate_pairs
from analysis.perspective_ledger import record_comparison


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        a = {"proposition_id": "p1", "statement": "Method A is stable", "source_ids": ["s1"], "context": {"framework": "F1"}}
        b = {"proposition_id": "p2", "statement": "Method A is unstable", "source_ids": ["s2"], "context": {"framework": "F2"}}
        _assert(_comparison_id(a, b) == _comparison_id(b, a), "Comparison identity is order-dependent.")

        normalized = normalize_comparison({"relationship": "different_framework", "confidence": 2.0, "different_context": "F2"})
        _assert(normalized["relationship"] == "different_framework", "Relationship normalization failed.")
        _assert(normalized["confidence"] == 1.0, "Confidence bounds failed.")
        _assert(normalized["different_context"] == ["F2"], "Context normalization failed.")

        propositions = [
            a,
            b,
            {"proposition_id": "p3", "statement": "Method A is stable", "source_ids": ["s1"]},
        ]
        pairs = candidate_pairs(propositions, max_pairs=4, minimum_overlap=0.15)
        pair_ids = {tuple(sorted((left["proposition_id"], right["proposition_id"]))) for left, right in pairs}
        _assert(("p1", "p2") in pair_ids, "Cross-source candidate was not selected.")
        _assert(("p1", "p3") not in pair_ids, "Same-source propositions were paired.")

        state = {}
        record_comparison(state, {"comparison_id": "cmp-skip", "skipped": True, "comparison": {"relationship": "appears_to_contradict"}})
        _assert("perspective_comparisons" not in state, "Skipped comparison was persisted.")
        record_comparison(state, {"comparison_id": "cmp-1", "proposition_ids": ["p2", "p1"], "source_ids": ["s2", "s1"], "comparison": {"relationship": "different_framework", "confidence": 0.8}}, max_records=2)
        _assert(len(state["perspective_comparisons"]) == 1, "Valid comparison was not persisted.")

        print("Stage 5 combined runtime audit")
        print("===============================")
        print("PASS: comparison identity, context normalization, candidate selection, and comparison persistence passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 5 AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
