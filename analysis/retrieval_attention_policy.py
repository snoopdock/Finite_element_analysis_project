#!/usr/bin/env python3
"""Deterministic interpretation of R7A retrieval context into process attention."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Dict, List, Mapping, Tuple


POLICY_SCHEMA_VERSION = 1
DEFAULT_UNAVAILABLE_STATUSES = {
    "rate_limited",
    "network_error",
    "server_error",
    "client_error",
    "http_error",
    "invalid_response",
    "exception",
    "starting",
    "unknown",
}


def _require_policy(policy: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(policy, Mapping):
        raise TypeError("policy must be a mapping")

    required = (
        "policy_version",
        "history_window_events",
        "repeated_non_success_threshold",
        "repeated_empty_result_threshold",
    )
    missing = [key for key in required if key not in policy]
    if missing:
        raise ValueError(f"missing policy fields: {missing}")

    result = dict(policy)
    if not str(result["policy_version"]).strip():
        raise ValueError("policy_version must not be empty")
    for key in required[1:]:
        try:
            value = int(result[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be an integer") from exc
        if value < 1:
            raise ValueError(f"{key} must be >= 1")
        result[key] = value
    return result


def _attention_id(
    policy: Mapping[str, Any],
    query_scope: str,
    provider: str,
    condition: str,
    supporting_event_ids: List[str],
) -> str:
    payload = {
        "policy_version": str(policy["policy_version"]),
        "query_scope": query_scope,
        "provider": provider,
        "observed_condition": condition,
        "supporting_event_ids": list(supporting_event_ids),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    digest = hashlib.sha256(encoded).hexdigest()[:24]
    return f"attention-{digest}"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _observation_class(item: Mapping[str, Any]) -> str:
    status = str(item.get("provider_status", "unknown")).strip().casefold()
    records = _safe_int(item.get("returned_records", 0), 0)
    if status == "success" and records > 0:
        return "success"
    if status == "success" and records == 0:
        return "empty_result"
    return "non_success"


def _latest_supporting_ids(observations: List[Dict[str, Any]]) -> List[str]:
    return [
        str(item.get("event_id", "")).strip()
        for item in observations
        if str(item.get("event_id", "")).strip()
    ]


def _reason(condition: str, query: str, provider: str, count: int | None = None) -> str:
    if condition == "provider_unavailable":
        return f"Provider {provider} is currently unavailable for query '{query}'."
    if condition == "provider_partially_available":
        return f"Provider availability is partial for query '{query}' on {provider}."
    if condition == "query_returned_empty_result":
        return f"Query '{query}' completed successfully on {provider} but returned no records."
    if condition == "repeated_query_provider_non_success":
        return (
            f"Query '{query}' has {count} non-success retrieval observations on "
            f"{provider} within the configured history window."
        )
    if condition == "repeated_query_provider_empty_result":
        return (
            f"Query '{query}' has {count} successful empty retrieval observations "
            f"on {provider} within the configured history window."
        )
    raise ValueError(f"unsupported attention condition: {condition}")


def _classify_current_condition(
    latest: Mapping[str, Any],
) -> str | None:
    status = str(latest.get("provider_status", "unknown")).strip().casefold()
    assessment = latest.get("acquisition_assessment", {})
    assessment_status = (
        str(assessment.get("status", "")).strip().casefold()
        if isinstance(assessment, Mapping)
        else ""
    )
    records = _safe_int(latest.get("returned_records", 0), 0)

    if status == "success":
        if records == 0:
            return "query_returned_empty_result"
        return None

    if assessment_status == "partial_provider_availability" and status not in {
        "rate_limited",
        "network_error",
        "server_error",
        "client_error",
        "http_error",
        "invalid_response",
        "exception",
    }:
        return "provider_partially_available"

    if status in DEFAULT_UNAVAILABLE_STATUSES or status != "success":
        return "provider_unavailable"
    return None


def evaluate_retrieval_attention(
    context: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> Dict[str, Any]:
    """Interpret an R7A context without mutating context, history, or scientific state."""
    if not isinstance(context, Mapping):
        raise TypeError("context must be a mapping")
    policy_data = _require_policy(policy)
    contexts = context.get("query_provider_contexts", [])
    if not isinstance(contexts, list):
        contexts = []

    output: List[Dict[str, Any]] = []
    window_size = policy_data["history_window_events"]

    for raw_context in contexts:
        if not isinstance(raw_context, Mapping):
            continue
        query = str(raw_context.get("query_scope", "")).strip()
        provider = str(raw_context.get("provider", "")).strip()
        observations = raw_context.get("observations", [])
        if not query or not provider or not isinstance(observations, list) or not observations:
            continue

        ordered = [deepcopy(item) for item in observations if isinstance(item, Mapping)]
        if not ordered:
            continue
        window = ordered[-window_size:]
        latest = window[-1]
        condition = _classify_current_condition(latest)

        if condition is not None:
            supporting = _latest_supporting_ids(
                window if condition.startswith("repeated_") else [latest]
            )
            count = None
            if condition.startswith("repeated_"):
                target_class = (
                    "non_success"
                    if condition == "repeated_query_provider_non_success"
                    else "empty_result"
                )
                count = sum(_observation_class(item) == target_class for item in window)
            attention = {
                "attention_id": _attention_id(
                    policy_data, query, provider, condition, supporting
                ),
                "policy_version": str(policy_data["policy_version"]),
                "query_scope": query,
                "provider": provider,
                "attention_reason": _reason(condition, query, provider, count),
                "observed_condition": condition,
                "lifecycle_status": "open",
                "supporting_event_ids": supporting,
            }
            output.append(attention)
            continue

        non_success_count = sum(
            _observation_class(item) == "non_success" for item in window
        )
        empty_count = sum(
            _observation_class(item) == "empty_result" for item in window
        )

        condition = None
        count = None
        if non_success_count >= policy_data["repeated_non_success_threshold"]:
            condition = "repeated_query_provider_non_success"
            count = non_success_count
        elif empty_count >= policy_data["repeated_empty_result_threshold"]:
            condition = "repeated_query_provider_empty_result"
            count = empty_count

        if condition is None:
            continue

        # A latest success-with-records observation is a recovery boundary: it
        # prevents older failures/empty results from being the sole current
        # basis for unconditional attention.
        if _observation_class(latest) == "success":
            continue

        supporting = _latest_supporting_ids(window)
        output.append(
            {
                "attention_id": _attention_id(
                    policy_data, query, provider, condition, supporting
                ),
                "policy_version": str(policy_data["policy_version"]),
                "query_scope": query,
                "provider": provider,
                "attention_reason": _reason(condition, query, provider, count),
                "observed_condition": condition,
                "lifecycle_status": "open",
                "supporting_event_ids": supporting,
            }
        )

    return {
        "schema_version": POLICY_SCHEMA_VERSION,
        "policy_version": str(policy_data["policy_version"]),
        "attention_items": output,
    }
