#!/usr/bin/env python3
"""Read-only Stage 3 diversity-selection audit.

Run from the repository root:
    python scripts/audit_stage3_diversity.py
"""

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
            {"source_id": "a", "provider_names": ["arxiv"], "source_types": ["preprint"], "ranking": {"score": 0.90}},
            {"source_id": "b", "provider_names": ["arxiv"], "source_types": ["preprint"], "ranking": {"score": 0.89}},
            {"source_id": "c", "provider_names": ["semantic_scholar"], "source_types": ["academic"], "ranking": {"score": 0.88}},
        ]
        selected = select_diverse_evidence(ranked, max_items=2, max_per_provider=1, max_per_source_type=2)
        _assert(len(selected) == 2, "Diversity selector returned the wrong number of items.")
        _assert({item["source_id"] for item in selected} == {"a", "c"}, "Diversity selector did not preserve provider diversity.")

        empty = select_diverse_evidence(ranked, max_items=0)
        _assert(empty == [], "Zero-item limit did not return an empty result.")

        print("Stage 3 diversity runtime audit")
        print("================================")
        print("PASS: bounded selection, provider diversity, and zero-limit behavior passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 3 DIVERSITY AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
