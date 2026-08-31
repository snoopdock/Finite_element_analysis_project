#!/usr/bin/env python3
"""Compatibility adapter for the graph-native perspective service."""

from __future__ import annotations

from typing import Any, Dict, List

from analysis.perspective_service import compare_graph_propositions


def record_perspective_jobs(
    state: Dict[str, Any],
    jobs: List[Dict],
    provider,
    parser,
    *,
    max_jobs: int = 2,
    model: str | None = None,
) -> Dict[str, Any]:
    """Delegate targeted perspective jobs to the graph-native service.

    Each job is constrained to its supplied proposition IDs. If a job has no
    usable IDs, the service may fall back to bounded deterministic discovery.
    No proposition is created from verifier summaries or correction-job text.
    """
    reports: List[Dict[str, Any]] = []
    jobs_checked = 0
    relationships_added = 0
    limit = max(0, int(max_jobs))

    for job in (jobs or [])[:limit]:
        if not isinstance(job, dict) or provider.budget_exhausted():
            break

        proposition_ids = job.get("proposition_ids", [])
        if isinstance(proposition_ids, str):
            proposition_ids = [proposition_ids]
        if not isinstance(proposition_ids, list):
            proposition_ids = []

        result = compare_graph_propositions(
            state,
            provider,
            parser,
            max_pairs=1,
            model=model,
            max_tokens=600,
            target_proposition_ids=[str(value).strip() for value in proposition_ids if str(value).strip()],
        )

        jobs_checked += 1
        relationships_added += int(result.get("relationships_added", 0))
        reports.extend(result.get("records", []))

    return {
        "jobs_checked": jobs_checked,
        "relationships_added": relationships_added,
        "reports": reports,
    }
