#!/usr/bin/env python3
"""Read-only Stage 3 evidence-selection audit."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.diversity import select_diverse_evidence


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        ranked = [
            {"source_id": "a", "provider_names": ["arxiv"], "source_types": ["preprint"], "ranking": {"score": 0.95}},
            {"source_id": "b", "provider_names": ["arxiv"], "source_types": ["preprint"], "ranking": {"score": 0.94}},
            {"source_id": "c", "provider_names": ["semantic_scholar"], "source_types": ["academic"], "ranking": {"score": 0.93}},
            {"source_id": "d", "provider_names": ["arxiv", "semantic_scholar"], "source_types": ["preprint", "academic"], "ranking": {"score": 0.92}},
        ]
        selected = select_diverse_evidence(
            ranked,
            max_items=3,
            max_per_provider=2,
            max_per_source_type=3,
        )
        _assert(len(selected) == 3, "Selection did not fill the requested evidence budget.")
        _assert({item["source_id"] for item in selected} == {"a", "b", "c"}, "Ranking/diversity selection unexpectedly displaced top evidence.")

        print("Stage 3 selection runtime audit")
        print("================================")
        print("PASS: ranked selection and provider/type constraints behaved as configured.")
        return 0
    except Exception as exc:
        print(f"STAGE 3 SELECTION AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
