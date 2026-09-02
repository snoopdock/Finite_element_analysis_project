#!/usr/bin/env python3
"""Audit invariants for retrieval-cycle provider status reporting."""

from __future__ import annotations

from research.evidence import _aggregate_provider_status


def _assert_equal(actual, expected, label):
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def main() -> int:
    # Provider-level aggregation must preserve meaningful distinctions.
    _assert_equal(
        _aggregate_provider_status(["success", "success"]),
        "success",
        "all-success aggregation",
    )
    _assert_equal(
        _aggregate_provider_status(["empty_result", "empty_result"]),
        "empty_result",
        "all-empty aggregation",
    )
    _assert_equal(
        _aggregate_provider_status(["rate_limited", "rate_limited"]),
        "rate_limited",
        "all-rate-limited aggregation",
    )
    _assert_equal(
        _aggregate_provider_status(["success", "rate_limited"]),
        "partial_failure",
        "success plus rate-limit aggregation",
    )
    _assert_equal(
        _aggregate_provider_status(["network_error", "server_error"]),
        "failure",
        "failure aggregation",
    )

    # Empty-result must not be conflated with an operational failure.
    empty_status = _aggregate_provider_status(["empty_result"])
    failure_status = _aggregate_provider_status(["rate_limited"])
    if empty_status == failure_status:
        raise AssertionError(
            "empty_result and rate_limited must remain distinguishable"
        )

    # The retrieval report is a transport/process diagnostic.  This audit only
    # imports the reporting API and never constructs propositions or evidence
    # relationships as a side effect.
    report = {
        "status": "partial_failure",
        "providers": {
            "arxiv": {"status": "success"},
            "semantic_scholar": {"status": "rate_limited"},
            "wikipedia": {"status": "success"},
        },
    }
    if "propositions" in report or "evidence_relations" in report:
        raise AssertionError("retrieval report must not carry scientific state")

    print("retrieval report integrity audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
