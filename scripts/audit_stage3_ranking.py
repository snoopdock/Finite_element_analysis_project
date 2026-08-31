#!/usr/bin/env python3
"""Read-only Stage 3 ranking audit.

Run from the repository root:
    python scripts/audit_stage3_ranking.py

Uses in-memory records only; it never calls external services or writes state.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.ranking import rank_items, rank_items_for_queries, source_quality_score


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        items = [
            {"source_id": "a", "title": "Galerkin stability", "abstract": "stability weak formulation", "source_types": ["preprint"], "provider_names": ["arxiv"]},
            {"source_id": "b", "title": "Galerkin stability review", "abstract": "stability and convergence", "source_types": ["journal"], "provider_names": ["semantic_scholar"]},
        ]
        ranked = rank_items("Galerkin stability", items, top_k=2)
        _assert(len(ranked) == 2, "Ranking returned the wrong item count.")
        for item in ranked:
            score = item["ranking"]["score"]
            _assert(0.0 <= score <= 1.0, "Ranking score escaped expected bounds.")
            weights = item["ranking"]["weights"]
            _assert(abs(sum(weights.values()) - 1.0) < 1e-9, "Ranking weights were not normalized.")

        multi = rank_items_for_queries(
            ["Galerkin stability", "weak formulation"],
            items,
            top_k=2,
        )
        _assert(len(multi) == 2, "Multi-query ranking returned the wrong item count.")
        for item in multi:
            ranking = item["ranking"]
            _assert(ranking.get("best_query"), "Best query provenance was lost.")
            _assert(len(ranking.get("per_query_scores", {})) >= 1, "Per-query ranking scores were lost.")

        mixed = dict(items[0])
        mixed["source_types"] = ["preprint", "journal"]
        _assert(source_quality_score(mixed) >= source_quality_score(items[0]), "Known stronger provenance did not improve quality prior.")

        print("Stage 3 ranking runtime audit")
        print("==============================")
        print("PASS: bounded scores, normalized weights, multi-query provenance, and quality-prior aggregation passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 3 RANKING AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
