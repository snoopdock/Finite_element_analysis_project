#!/usr/bin/env python3
"""Read-only retrieval coverage assessment.

This module translates operational retrieval outcomes into an acquisition
status without making claims about scientific truth, literature absence, or
knowledge quality.
"""

from __future__ import annotations

from typing import Dict


KNOWN_OPERATIONAL_STATUSES = {
    "success",
    "empty_result",
    "rate_limited",
    "partial_failure",
    "failure",
    "mixed",
}


def assess_retrieval_coverage(report: Dict) -> Dict:
    """Assess evidence-acquisition completeness from a retrieval report.

    The result is descriptive only. It does not change ranking, convergence,
    epistemic state, propositions, or writing decisions.
    """
    if not isinstance(report, dict):
        return {
            "status": "not_defined_yet",
            "operational_status": "unknown",
            "available_provider_count": 0,
            "unavailable_provider_count": 0,
            "returned_records": 0,
            "selected_records": 0,
        }

    operational_status = str(report.get("status", "unknown")).strip()
    providers = report.get("providers", {})
    if not isinstance(providers, dict):
        providers = {}

    provider_statuses = []
    for provider in providers.values():
        if not isinstance(provider, dict):
            continue
        provider_statuses.append(str(provider.get("status", "unknown")).strip())

    unavailable_statuses = {
        "rate_limited",
        "partial_failure",
        "failure",
        "mixed",
        "exception",
        "network_error",
        "server_error",
        "client_error",
        "http_error",
        "invalid_response",
    }

    available_provider_count = sum(
        1 for status in provider_statuses
        if status in {"success", "empty_result"}
    )
    unavailable_provider_count = sum(
        1 for status in provider_statuses
        if status in unavailable_statuses
    )

    try:
        returned_records = int(report.get("returned_records", 0) or 0)
    except (TypeError, ValueError):
        returned_records = 0

    try:
        selected_records = int(report.get("selected_records", 0) or 0)
    except (TypeError, ValueError):
        selected_records = 0

    if not providers:
        coverage_status = "not_defined_yet"
    elif unavailable_provider_count > 0:
        coverage_status = "partial_provider_availability"
    elif operational_status == "empty_result" and returned_records == 0:
        coverage_status = "no_evidence_returned"
    else:
        coverage_status = "not_defined_yet"

    return {
        "status": coverage_status,
        "operational_status": operational_status,
        "available_provider_count": available_provider_count,
        "unavailable_provider_count": unavailable_provider_count,
        "returned_records": returned_records,
        "selected_records": selected_records,
    }
