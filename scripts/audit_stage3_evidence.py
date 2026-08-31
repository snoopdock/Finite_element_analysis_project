#!/usr/bin/env python3
"""Read-only Stage 3 evidence/provenance audit.

Run from the repository root:
    python scripts/audit_stage3_evidence.py

Uses in-memory records only; it never calls external services or writes project state.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.evidence import merge_evidence


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        old = [
            {
                "source_id": "paper-1",
                "title": "Example paper",
                "query_contexts": ["finite element stability"],
                "provider_names": ["arxiv"],
                "source_types": ["preprint"],
                "retrieved_at": "2026-08-31T00:00:00+00:00",
            }
        ]
        new = [
            {
                "source_id": "paper-1",
                "title": "Example paper",
                "query_contexts": ["Galerkin stability"],
                "provider_names": ["semantic_scholar"],
                "source_types": ["academic"],
                "retrieved_at": "2026-08-31T00:01:00+00:00",
            },
            {
                "source_id": "paper-2",
                "title": "Second paper",
                "query_contexts": ["weak formulation"],
                "provider_names": ["wikipedia"],
                "source_types": ["wikipedia"],
                "retrieved_at": "2026-08-31T00:02:00+00:00",
            },
        ]

        merged = merge_evidence(old, new, max_keep=10)
        by_id = {item["source_id"]: item for item in merged}
        _assert(set(by_id) == {"paper-1", "paper-2"}, "Source identity merge failed.")
        _assert(set(by_id["paper-1"]["query_contexts"]) == {"finite element stability", "Galerkin stability"}, "Query provenance was lost.")
        _assert(set(by_id["paper-1"]["provider_names"]) == {"arxiv", "semantic_scholar"}, "Provider provenance was lost.")
        _assert(set(by_id["paper-1"]["source_types"]) == {"preprint", "academic"}, "Source-type provenance was lost.")
        _assert(len(merged) == 2, "Duplicate source IDs were not collapsed.")

        reversed_merge = merge_evidence(new, old, max_keep=10)
        reverse_by_id = {item["source_id"]: item for item in reversed_merge}
        _assert(
            by_id["paper-1"]["query_contexts"] == reverse_by_id["paper-1"]["query_contexts"],
            "Merge result depends on input order.",
        )
        _assert(
            by_id["paper-1"]["provider_names"] == reverse_by_id["paper-1"]["provider_names"],
            "Provider merge depends on input order.",
        )

        print("Stage 3 evidence runtime audit")
        print("===============================")
        print("PASS: source identity, provenance accumulation, deduplication, and order independence passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 3 EVIDENCE AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
