#!/usr/bin/env python3
"""Read-only reconstruction of retrieval acquisition history events."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


REQUIRED_EVENT_FIELDS = (
    "event_id",
    "cycle",
    "retrieved_at",
    "query_scope",
    "report",
    "acquisition_assessment",
    "schema_version",
)


def replay_retrieval_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Reconstruct the recorded retrieval process from one persisted event.

    This function is intentionally read-only and performs no network access.
    The replay is a faithful structural reconstruction, not a re-computation
    of provider results.
    """
    if not isinstance(event, dict):
        raise TypeError("Retrieval event must be a dictionary.")

    missing = [field for field in REQUIRED_EVENT_FIELDS if field not in event]
    if missing:
        raise ValueError(
            "Retrieval event is missing required fields: "
            + ", ".join(missing)
        )

    report = event.get("report")
    if not isinstance(report, dict):
        raise ValueError("Retrieval event report must be a dictionary.")

    providers = report.get("providers", {})
    if not isinstance(providers, dict):
        providers = {}

    provider_replay = {}
    for provider_name, provider_data in providers.items():
        if not isinstance(provider_data, dict):
            provider_replay[str(provider_name)] = {
                "status": "unknown",
            }
            continue

        provider_replay[str(provider_name)] = {
            "status": provider_data.get("status", "unknown"),
            "attempts": provider_data.get("attempts", 0),
            "queries": deepcopy(provider_data.get("queries", [])),
            "returned_records": provider_data.get("returned_records", 0),
        }

    return {
        "event_id": event["event_id"],
        "cycle": event["cycle"],
        "retrieved_at": event["retrieved_at"],
        "query_scope": deepcopy(event["query_scope"]),
        "provider_operations": provider_replay,
        "operational_status": report.get("status", "unknown"),
        "returned_records": report.get("returned_records", 0),
        "selected_records": report.get("selected_records", 0),
        "acquisition_assessment": deepcopy(
            event["acquisition_assessment"]
        ),
        "schema_version": event["schema_version"],
    }
