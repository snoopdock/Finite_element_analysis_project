#!/usr/bin/env python3
"""Build auditable retrieval acquisition events from current retrieval state."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable
from uuid import uuid4

from analysis.retrieval_coverage import assess_retrieval_coverage
from utils.text import utcnow


EVENT_SCHEMA_VERSION = 1


def _normalize_query_scope(queries: Iterable[Any]) -> list[str]:
    """Return normalized, case-insensitive unique query strings in order."""
    if queries is None:
        return []

    result: list[str] = []
    seen: set[str] = set()
    for query in queries:
        text = str(query).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _queries_from_report(report: Dict[str, Any]) -> list[str]:
    """Extract the final query scope from provider-level retrieval reporting."""
    queries: list[str] = []
    for provider in report.get("providers", {}).values():
        if not isinstance(provider, dict):
            continue
        provider_queries = provider.get("queries", [])
        if not isinstance(provider_queries, list):
            continue
        queries.extend(provider_queries)
    return _normalize_query_scope(queries)


def create_retrieval_event(
    cycle: int,
    queries: Iterable[Any] | None,
    report: Dict[str, Any],
) -> Dict[str, Any]:
    """Create one event for one retrieval invocation."""
    if not isinstance(report, dict):
        raise TypeError("Retrieval report must be a dictionary.")

    query_scope = _normalize_query_scope(queries or [])
    if not query_scope:
        query_scope = _queries_from_report(report)

    return {
        "event_id": f"retrieval-{uuid4()}",
        "cycle": int(cycle),
        "retrieved_at": utcnow(),
        "query_scope": query_scope,
        "report": deepcopy(report),
        "acquisition_assessment": assess_retrieval_coverage(
            deepcopy(report)
        ),
        "schema_version": EVENT_SCHEMA_VERSION,
    }
