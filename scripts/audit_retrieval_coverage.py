#!/usr/bin/env python3
"""Audit the read-only retrieval coverage assessment boundary."""

from __future__ import annotations

from analysis.retrieval_coverage import assess_retrieval_coverage


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    all_success = assess_retrieval_coverage({
        "status": "success",
        "returned_records": 4,
        "selected_records": 4,
        "providers": {
            "arxiv": {"status": "success"},
            "wikipedia": {"status": "success"},
        },
    })
    _assert(all_success["status"] == "not_defined_yet", "success must not imply coverage completeness")
    _assert(all_success["operational_status"] == "success", "operational status must be preserved")

    empty = assess_retrieval_coverage({
        "status": "empty_result",
        "returned_records": 0,
        "selected_records": 0,
        "providers": {
            "arxiv": {"status": "empty_result"},
            "wikipedia": {"status": "empty_result"},
        },
    })
    _assert(empty["status"] == "no_evidence_returned", "successful empty retrieval must be distinguishable")

    partial = assess_retrieval_coverage({
        "status": "partial_failure",
        "returned_records": 2,
        "selected_records": 2,
        "providers": {
            "arxiv": {"status": "success"},
            "semantic_scholar": {"status": "rate_limited"},
            "wikipedia": {"status": "success"},
        },
    })
    _assert(partial["status"] == "partial_provider_availability", "mixed provider cycle must expose acquisition limitation")
    _assert(partial["available_provider_count"] == 2, "available provider count is incorrect")
    _assert(partial["unavailable_provider_count"] == 1, "unavailable provider count is incorrect")
    _assert(partial["operational_status"] == "partial_failure", "partial failure must be preserved")

    limited = assess_retrieval_coverage({
        "status": "rate_limited",
        "returned_records": 0,
        "selected_records": 0,
        "providers": {
            "semantic_scholar": {"status": "rate_limited"},
        },
    })
    _assert(limited["status"] == "partial_provider_availability", "rate limiting must be an acquisition limitation")
    _assert(limited["status"] != "no_evidence_returned", "rate limiting must not mean evidence absence")

    malformed = assess_retrieval_coverage(None)
    _assert(malformed["status"] == "not_defined_yet", "malformed reports must remain non-assertive")

    print("retrieval coverage audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
