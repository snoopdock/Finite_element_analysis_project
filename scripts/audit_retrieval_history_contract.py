#!/usr/bin/env python3
"""Audit the R6 retrieval acquisition history contract."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "specs" / "contracts" / "retrieval_history_contract.yaml"


def main() -> int:
    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))

    assert contract["version"] == 1
    assert contract["state_field"]["name"] == "retrieval_history"
    assert contract["state_field"]["shape"]["events"] == "list"

    required = contract["retrieval_event"]["required_fields"]
    assert required == [
        "event_id",
        "cycle",
        "retrieved_at",
        "report",
        "acquisition_assessment",
    ]

    temporal_rules = contract["temporal_rules"]
    assert any("never overwritten" in rule for rule in temporal_rules)
    assert any("does not erase" in rule for rule in temporal_rules)
    assert any("must not duplicate" in rule for rule in temporal_rules)

    idempotency_rules = contract["idempotency_rules"]
    assert any("at most once" in rule for rule in idempotency_rules)
    assert any("new event_id" in rule for rule in idempotency_rules)

    granularity = contract["granularity"]
    assert any("query-level" in rule for rule in granularity)
    assert any("provider-level" in rule for rule in granularity)

    separation_rules = contract["separation_rules"]
    assert any("not evidence" in rule for rule in separation_rules)
    assert any("propositions" in rule and "epistemic state" in rule for rule in separation_rules)

    excluded = set(contract["scope"]["excluded"])
    assert "literature_coverage_status" in excluded
    assert "ranking changes" in excluded
    assert "convergence changes" in excluded
    assert "writer decisions" in excluded
    assert "semantic claim verification" in excluded

    print("R6 retrieval history contract audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
