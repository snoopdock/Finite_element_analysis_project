#!/usr/bin/env python3
"""Compatibility adapter for the graph-native perspective service."""

from __future__ import annotations

from typing import Any, Dict, List

from analysis.perspective_service import compare_graph_propositions


def _target_ids_from_job(state: Dict[str, Any], job: Dict[str, Any]) -> List[str]:
    """Resolve a perspective job to graph proposition IDs using provenance."""
    explicit = job.get("proposition_ids", [])
    if isinstance(explicit, str):
        explicit = [explicit]
    if isinstance(explicit, list):
        explicit = [str(value).strip() for value in explicit if str(value).strip()]
        if explicit:
            return explicit

    graph = state.get("knowledge_graph", {}) if isinstance(state, dict) else {}
    propositions = graph.get("propositions", {}) if isinstance(graph, dict) else {}
    if not isinstance(propositions, dict):
        return []

    source_ids = set()
    for value in job.get("citation_ids", []) or []:
        value = str(value).strip()
        if value:
            source_ids.add(value)
    for report in job.get("source_reports", []) or []:
        if not isinstance(report, dict):
            continue
        value = str(report.get("source_id", "")).strip()
        if value:
            source_ids.add(value)

    if not source_ids:
        return []

    candidates = []
    for proposition in propositions.values():
        if not isinstance(proposition, dict):
            continue
        proposition_id = str(proposition.get("proposition_id", "")).strip()
        proposition_sources = {
            str(value).strip()
            for value in proposition.get("source_ids", []) or []
            if str(value).strip()
        }
        overlap = len(source_ids & proposition_sources)
        if proposition_id and overlap:
            candidates.append((overlap, proposition_id))

    candidates.sort(key=lambda item: (-item[0], item[1]))
    return [proposition_id for _, proposition_id in candidates[:2]]


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

    A job must resolve to at least two existing graph propositions. Missing or
    invalid provenance therefore produces no comparison rather than falling back
    to unrelated global discovery.
    """
    reports: List[Dict[str, Any]] = []
    jobs_checked = 0
    relationships_added = 0
    limit = max(0, int(max_jobs))

    for job in (jobs or [])[:limit]:
        if not isinstance(job, dict) or provider.budget_exhausted():
            break

        proposition_ids = _target_ids_from_job(state, job)
        if len(proposition_ids) < 2:
            reports.append({
                "section_id": job.get("section_id"),
                "status": "insufficient_provenance",
                "proposition_ids": proposition_ids,
            })
            jobs_checked += 1
            continue

        result = compare_graph_propositions(
            state,
            provider,
            parser,
            max_pairs=1,
            model=model,
            max_tokens=600,
            target_proposition_ids=proposition_ids,
        )

        jobs_checked += 1
        relationships_added += int(result.get("relationships_added", 0))
        reports.extend(result.get("records", []))

    return {
        "jobs_checked": jobs_checked,
        "relationships_added": relationships_added,
        "reports": reports,
    }
