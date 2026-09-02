#!/usr/bin/env python3
"""Audit the R4 separation between retrieval operation and evidence coverage."""

from __future__ import annotations

from pathlib import Path

import yaml


CONTRACT = (
    Path(__file__).resolve().parents[1]
    / "specs"
    / "contracts"
    / "retrieval_coverage_contract.yaml"
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    data = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    _assert(
        isinstance(data, dict),
        "retrieval coverage contract must be a mapping",
    )
    _assert(
        data.get("version") == 1,
        "retrieval coverage contract version must be 1",
    )

    operational = data.get("operational_status", {})
    coverage = data.get("coverage_status", {})
    rules = data.get("rules", [])

    required_operational = {
        "success",
        "empty_result",
        "rate_limited",
        "partial_failure",
        "failure",
        "mixed",
    }
    required_coverage = {
        "not_defined_yet",
        "partial_provider_availability",
        "no_evidence_returned",
    }

    _assert(
        required_operational.issubset(operational),
        "missing operational status vocabulary",
    )
    _assert(
        required_coverage.issubset(coverage),
        "missing coverage status vocabulary",
    )
    _assert(
        isinstance(rules, list) and len(rules) >= 5,
        "coverage boundary rules are incomplete",
    )

    # Operational failure and evidence absence must remain distinct concepts.
    _assert(
        operational["rate_limited"]["meaning"]
        != operational["empty_result"]["meaning"],
        "rate_limited must not be equivalent to empty_result",
    )

    examples = data.get("examples", {})
    mixed = examples.get("mixed_provider_cycle", {})
    _assert(
        mixed.get("operational_status") == "partial_failure",
        "mixed cycle must be partial_failure",
    )
    _assert(
        mixed.get("coverage_status") == "partial_provider_availability",
        "mixed cycle must expose an acquisition limitation",
    )

    text_rules = "\n".join(str(rule) for rule in rules).lower()
    _assert(
        "does not modify ranking" in text_rules,
        "R4 contract must explicitly defer ranking behavior",
    )
    _assert(
        "does not modify convergence" in text_rules,
        "R4 contract must explicitly defer convergence behavior",
    )
    _assert(
        "scientific conclusions" in text_rules,
        "R4 contract must prohibit treating provider failure as scientific conclusion",
    )

    print("retrieval coverage contract audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
