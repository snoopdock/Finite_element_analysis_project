#!/usr/bin/env python3
"""Read-only normalization of retrieval history for future attention logic."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Tuple


CONTEXT_SCHEMA_VERSION = 1
REQUIRED_EVENT_FIELDS = (
    "event_id",
    "cycle",
    "retrieved_at",
    "query_scope",
    "report",
    "acquisition_assessment",
)


def _normalize_text(value: Any) -> str:
    return str(value).strip()


def _normalize_query_scope(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values or []:
        text = _normalize_text(value)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _history_events(history: Any) -> List[Dict[str, Any]]:
    if isinstance(history, dict):
        history = history.get("events", [])
    if not isinstance(history, list):
        return []
    return [deepcopy(event) for event in history if isinstance(event, dict)]


def _event_sort_key(event: Dict[str, Any]) -> Tuple[int, str, str]:
    try:
        cycle = int(event.get("cycle", 0))
    except (TypeError, ValueError):
        cycle = 0
    return (
        cycle,
        _normalize_text(event.get("retrieved_at", "")),
        _normalize_text(event.get("event_id", "")),
    )


def _provider_queries(
    event: Dict[str, Any],
    provider_data: Dict[str, Any],
) -> List[str]:
    queries = provider_data.get("queries")
    if isinstance(queries, list):
        return _normalize_query_scope(queries)

    # A missing provider-level query list is deliberately not inferred from
    # the event-level scope. R7A must not invent query/provider associations.
    return []


def _provider_observation(
    event: Dict[str, Any],
    provider_data: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "event_id": _normalize_text(event.get("event_id", "")),
        "cycle": event.get("cycle"),
        "retrieved_at": event.get("retrieved_at"),
        "provider_status": provider_data.get("status", "unknown"),
        "attempts": provider_data.get("attempts", 0),
        "returned_records": provider_data.get("returned_records", 0),
        "acquisition_assessment": deepcopy(
            event.get("acquisition_assessment", {})
        ),
    }


def build_retrieval_attention_context(
    retrieval_history: Any,
) -> Dict[str, Any]:
    """Normalize persisted retrieval history into query/provider observations.

    This function is intentionally non-interpretive. It does not determine
    whether attention is required, whether a condition is resolved, or what
    action should be taken. It only organizes recorded retrieval observations
    for a later policy layer.
    """
    events = _history_events(retrieval_history)
    events.sort(key=_event_sort_key)

    grouped: Dict[Tuple[str, str], Dict[str, Any]] = {}
    unscoped_provider_operations: List[Dict[str, Any]] = []
    unscoped_events: List[Dict[str, Any]] = []

    for event in events:
        report = event.get("report")
        if not isinstance(report, dict):
            unscoped_events.append(
                {
                    "event_id": _normalize_text(event.get("event_id", "")),
                    "cycle": event.get("cycle"),
                    "retrieved_at": event.get("retrieved_at"),
                    "query_scope": _normalize_query_scope(
                        event.get("query_scope", [])
                        if isinstance(event.get("query_scope"), list)
                        else []
                    ),
                }
            )
            continue

        providers = report.get("providers", {})
        if not isinstance(providers, dict) or not providers:
            unscoped_events.append(
                {
                    "event_id": _normalize_text(event.get("event_id", "")),
                    "cycle": event.get("cycle"),
                    "retrieved_at": event.get("retrieved_at"),
                    "query_scope": _normalize_query_scope(
                        event.get("query_scope", [])
                        if isinstance(event.get("query_scope"), list)
                        else []
                    ),
                    "operational_status": report.get("status", "unknown"),
                }
            )
            continue

        for provider_name, raw_provider in providers.items():
            provider = raw_provider if isinstance(raw_provider, dict) else {}
            provider_text = _normalize_text(provider_name)
            observation = _provider_observation(event, provider)
            queries = _provider_queries(event, provider)

            if not provider_text or not queries:
                unscoped_provider_operations.append(
                    {
                        **observation,
                        "provider": provider_text,
                        "query_scope": queries,
                    }
                )
                continue

            for query in queries:
                key = (query.casefold(), provider_text.casefold())
                context = grouped.setdefault(
                    key,
                    {
                        "query_scope": query,
                        "provider": provider_text,
                        "observations": [],
                        "supporting_event_ids": [],
                    },
                )
                context["observations"].append(deepcopy(observation))
                event_id = observation["event_id"]
                if event_id and event_id not in context["supporting_event_ids"]:
                    context["supporting_event_ids"].append(event_id)

    contexts = list(grouped.values())
    for context in contexts:
        context["observations"].sort(
            key=lambda item: (
                int(item.get("cycle", 0))
                if str(item.get("cycle", "")).lstrip("-").isdigit()
                else 0,
                _normalize_text(item.get("retrieved_at", "")),
                _normalize_text(item.get("event_id", "")),
            )
        )
        context["supporting_event_ids"] = [
            item["event_id"]
            for item in context["observations"]
            if item.get("event_id")
        ]
        if context["observations"]:
            context["latest_observation"] = deepcopy(
                context["observations"][-1]
            )

    contexts.sort(
        key=lambda item: (
            item["query_scope"].casefold(),
            item["provider"].casefold(),
        )
    )
    unscoped_provider_operations.sort(
        key=lambda item: (
            int(item.get("cycle", 0))
            if str(item.get("cycle", "")).lstrip("-").isdigit()
            else 0,
            _normalize_text(item.get("provider", "")).casefold(),
            _normalize_text(item.get("event_id", "")),
        )
    )
    unscoped_events.sort(key=_event_sort_key)

    return {
        "schema_version": CONTEXT_SCHEMA_VERSION,
        "event_count": len(events),
        "query_provider_contexts": contexts,
        "unscoped_provider_operations": unscoped_provider_operations,
        "unscoped_events": unscoped_events,
    }
