#!/usr/bin/env python3
"""Combined read-only Stage 3 runtime smoke audit.

Run from the repository root:
    python scripts/audit_stage3.py

This audit uses only in-memory records and never performs network retrieval,
LLM calls, cache writes, or project-state writes.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.diversity import select_diverse_evidence
from research.evidence import merge_evidence, get_next_unread_content
from research.ranking import rank_items_for_queries


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        candidates = [
            {
                "source_id": "paper-a",
                "title": "Galerkin stability",
                "abstract": "weak formulation and stability",
                "query_contexts": ["Galerkin stability"],
                "provider_names": ["arxiv"],
                "source_types": ["preprint"],
            },
            {
                "source_id": "paper-b",
                "title": "Galerkin convergence",
                "abstract": "weak formulation and convergence",
                "query_contexts": ["weak formulation"],
                "provider_names": ["semantic_scholar"],
                "source_types": ["academic"],
            },
        ]

        ranked = rank_items_for_queries(
            ["Galerkin stability", "weak formulation"],
            candidates,
            top_k=len(candidates),
        )
        _assert(len(ranked) == 2, "Multi-query ranking lost candidates.")
        _assert(all(item.get("ranking", {}).get("best_query") for item in ranked), "Best-query provenance missing.")

        selected = select_diverse_evidence(
            ranked,
            max_items=2,
            max_per_provider=1,
            max_per_source_type=2,
        )
        _assert({item["source_id"] for item in selected} == {"paper-a", "paper-b"}, "Diversity selection discarded a distinct provider perspective.")

        merged = merge_evidence(
            candidates[:1],
            [dict(candidates[0], query_contexts=["third query"], ranking={"score": 0.9})],
            max_keep=10,
        )
        _assert(len(merged) == 1, "Merge duplicated a logical source.")
        _assert("third query" in merged[0]["query_contexts"], "Merge lost new provenance.")
        _assert(abs(merged[0]["ranking"]["score"] - 0.9) < 1e-12, "Merge lost fresh ranking metadata.")

        no_full_text = {"source_id": "paper-x", "title": "Abstract only"}
        _assert(get_next_unread_content(no_full_text, {}) is None, "Abstract-only evidence entered full-text reading path.")

        print("Stage 3 combined runtime smoke audit")
        print("====================================")
        print("PASS: ranking, provenance, diversity, merge refresh, and full-text gating checks passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 3 AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
