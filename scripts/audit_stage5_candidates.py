#!/usr/bin/env python3
"""Read-only audit for bounded perspective candidate selection."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.perspective_candidates import candidate_pairs


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        propositions = [
            {"proposition_id": "p1", "statement": "Method A is stable", "source_ids": ["s1"]},
            {"proposition_id": "p2", "statement": "Method A is unstable", "source_ids": ["s2"]},
            {"proposition_id": "p3", "statement": "Method A is stable", "source_ids": ["s1"]},
            {"proposition_id": "p4", "statement": "Completely different topic", "source_ids": ["s3"]},
        ]
        pairs = candidate_pairs(propositions, max_pairs=8, minimum_overlap=0.15)
        ids = [tuple(sorted((a["proposition_id"], b["proposition_id"]))) for a, b in pairs]
        _assert(("p1", "p2") in ids, "Expected cross-source candidate pair was not selected.")
        _assert(("p1", "p3") not in ids, "Same-source propositions were treated as independent perspectives.")
        _assert(len(pairs) <= 8, "Candidate-pair bound was exceeded.")
        print("Stage 5 candidate-selection runtime audit")
        print("==========================================")
        print("PASS: bounded, deterministic, cross-source candidate selection passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 5 CANDIDATE AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
