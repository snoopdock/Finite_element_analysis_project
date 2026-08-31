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
    """Preserve the historical API while delegating comparison to the graph service.

    Existing graph propositions are compared directly. No proposition is created from
    verifier summaries or correction-job text. ``jobs`` is retained only for API
    compatibility; the graph remains the authoritative source of propositions.
    """
    result = compare_graph_propositions(
        state,
        provider,
        parser,
        max_pairs=max(0, int(max_jobs)),
        model=model,
        max_tokens=600,
    )
    return {
        "jobs_checked": result.get("compared", 0),
        "relationships_added": result.get("relationships_added", 0),
        "reports": result.get("records", []),
    }
