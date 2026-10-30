#!/usr/bin/env python3
"""Fail-closed acceptance check for AE-32C batch-evaluation/v3 summaries."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "ae32c/batch-evaluation/v3"
REQUIRED_PROVIDERS = ("cloudflare", "nararouter", "openrouter")
PROVIDER_COUNT = len(REQUIRED_PROVIDERS)
PROVIDER_METRICS = (
    "baseline_completed",
    "graph_protocol_completed",
    "graph_evidence_complete",
    "overall_accepted_trials",
)


class BatchAcceptanceError(ValueError):
    """Raised when a batch summary is incomplete or fails an acceptance gate."""


def _count(summary: Mapping[str, Any], key: str) -> int:
    value = summary.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BatchAcceptanceError(
            f"Batch summary field {key!r} must be a non-negative integer."
        )
    return value


def _validate_provider_breakdown(
    summary: Mapping[str, Any], rounds: int, totals: Mapping[str, int]
) -> None:
    breakdown = summary.get("provider_breakdown")
    if not isinstance(breakdown, Mapping):
        raise BatchAcceptanceError("Batch summary provider_breakdown must be an object.")

    actual_providers = set(breakdown)
    expected_providers = set(REQUIRED_PROVIDERS)
    if actual_providers != expected_providers:
        missing = sorted(expected_providers - actual_providers)
        extra = sorted(actual_providers - expected_providers)
        raise BatchAcceptanceError(
            f"Provider breakdown mismatch; missing={missing}, unexpected={extra}."
        )

    sums = {metric: 0 for metric in PROVIDER_METRICS}
    for provider in REQUIRED_PROVIDERS:
        row = breakdown.get(provider)
        if not isinstance(row, Mapping):
            raise BatchAcceptanceError(
                f"Provider breakdown for {provider!r} must be an object."
            )
        provider_trials = _count(row, "trials")
        if provider_trials != rounds:
            raise BatchAcceptanceError(
                f"{provider} trial denominator mismatch: {provider_trials} of {rounds}."
            )
        for metric in PROVIDER_METRICS:
            value = _count(row, metric)
            sums[metric] += value
            if value != rounds:
                raise BatchAcceptanceError(
                    f"{provider} {metric} passed for {value} of {rounds} trials."
                )

    for metric, value in sums.items():
        if value != totals[metric]:
            raise BatchAcceptanceError(
                f"Provider breakdown {metric} sum {value} does not match "
                f"top-level {metric} {totals[metric]}."
            )


def validate_batch_summary(summary: Mapping[str, Any], rounds: int) -> dict[str, int]:
    if not isinstance(summary, Mapping):
        raise BatchAcceptanceError("Batch summary must be a JSON object.")
    if summary.get("schema_version") != SCHEMA_VERSION:
        raise BatchAcceptanceError(
            f"Unsupported batch-summary schema; expected {SCHEMA_VERSION}."
        )
    if isinstance(rounds, bool) or not isinstance(rounds, int) or not 1 <= rounds <= 4:
        raise BatchAcceptanceError("Rounds must be an integer from 1 through 4.")

    expected_from_dispatch = rounds * PROVIDER_COUNT
    expected = _count(summary, "expected_trials")
    observed = _count(summary, "observed_trials")
    baseline = _count(summary, "baseline_completed")
    graph_protocol = _count(summary, "graph_protocol_completed")
    graph_evidence = _count(summary, "graph_evidence_complete")
    accepted = _count(summary, "overall_accepted_trials")

    if expected != expected_from_dispatch:
        raise BatchAcceptanceError(
            f"Expected-trial denominator mismatch: summary={expected}, "
            f"dispatch={expected_from_dispatch}."
        )
    if observed != expected:
        raise BatchAcceptanceError(f"Observed {observed} of {expected} expected trials.")
    if baseline != expected:
        raise BatchAcceptanceError(
            f"Baseline completed for {baseline} of {expected} trials."
        )
    if graph_protocol != expected:
        raise BatchAcceptanceError(
            f"Graph protocol completed for {graph_protocol} of {expected} trials."
        )
    if graph_evidence != expected:
        raise BatchAcceptanceError(
            f"Graph evidence complete for {graph_evidence} of {expected} trials."
        )
    if accepted != expected:
        raise BatchAcceptanceError(
            f"Overall acceptance passed for {accepted} of {expected} trials."
        )
    if summary.get("passed") is not True:
        raise BatchAcceptanceError("Batch evaluator did not mark the batch as passed.")

    totals = {
        "baseline_completed": baseline,
        "graph_protocol_completed": graph_protocol,
        "graph_evidence_complete": graph_evidence,
        "overall_accepted_trials": accepted,
    }
    _validate_provider_breakdown(summary, rounds, totals)

    return {
        "expected_trials": expected,
        "observed_trials": observed,
        "baseline_completed": baseline,
        "graph_protocol_completed": graph_protocol,
        "graph_evidence_complete": graph_evidence,
        "overall_accepted_trials": accepted,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-summary", required=True, type=Path)
    parser.add_argument("--rounds", required=True, type=int)
    args = parser.parse_args(argv)
    if not args.batch_summary.is_file():
        raise SystemExit("Batch summary missing; cannot claim success.")
    try:
        summary = json.loads(args.batch_summary.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"Batch summary could not be read as JSON: {type(exc).__name__}."
        ) from None
    try:
        counts = validate_batch_summary(summary, args.rounds)
    except BatchAcceptanceError as exc:
        raise SystemExit(str(exc)) from None
    print("All AE-32C v3 batch acceptance gates passed.")
    print(json.dumps(counts, sort_keys=True))
    print("Causal accuracy still requires independent human review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
