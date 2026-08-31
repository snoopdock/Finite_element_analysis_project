#!/usr/bin/env python3
"""Read-only audit for Stage 5 provenance-to-proposition resolution."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.perspective_registry import _target_ids_from_job


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        p1 = "11111111-1111-4111-8111-111111111111"
        p2 = "22222222-2222-4222-8222-222222222222"
        p3 = "33333333-3333-4333-8333-333333333333"
        state = {
            "knowledge_graph": {
                "propositions": {
                    p1: {"proposition_id": p1, "source_ids": ["source-a"]},
                    p2: {"proposition_id": p2, "source_ids": ["source-b"]},
                    p3: {"proposition_id": p3, "source_ids": ["source-c"]},
                }
            }
        }

        explicit = _target_ids_from_job(
            state,
            {"proposition_ids": [p2, p1]},
        )
        check(explicit == [p2, p1], "Explicit proposition IDs were not preserved.")

        inferred = _target_ids_from_job(
            state,
            {"citation_ids": ["source-a", "source-b"]},
        )
        check(set(inferred) == {p1, p2}, "Proposition IDs were not inferred from provenance.")
        check(p3 not in inferred, "Unrelated proposition was selected.")

        incomplete = _target_ids_from_job(
            state,
            {"citation_ids": ["unknown-source"]},
        )
        check(incomplete == [], "Unknown provenance incorrectly triggered global fallback.")

        mixed = _target_ids_from_job(
            state,
            {"citation_ids": ["source-a"], "source_reports": [{"source_id": "source-b"}]},
        )
        check(set(mixed) == {p1, p2}, "Source-report provenance was not combined correctly.")

        print("Stage 5 target-resolution audit")
        print("================================")
        print("PASS: explicit IDs, provenance inference, unrelated-source exclusion, and missing-provenance safety passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 5 TARGET RESOLUTION AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
