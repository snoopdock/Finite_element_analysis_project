#!/usr/bin/env python3
"""Audit the H7 failure-classification matrix."""

from pathlib import Path

import yaml


MATRIX = Path(__file__).resolve().parents[1] / "audits" / "H7_failure_analysis_matrix.yaml"

REQUIRED_CODES = {
    "provenance_loss",
    "identity_drift",
    "evidence_scope_error",
    "validity_overreach",
    "perspective_collapse",
    "causal_overreach",
    "temporal_overreach",
    "consensus_inflation",
    "epistemic_leak",
    "serialization_loss",
}


def main() -> int:
    data = yaml.safe_load(MATRIX.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    failures = data.get("failure_classes", [])
    assert isinstance(failures, list)
    codes = {str(item.get("id", "")).strip() for item in failures if isinstance(item, dict)}
    missing = REQUIRED_CODES - codes
    assert not missing, f"Missing H7 failure classes: {sorted(missing)}"

    for item in failures:
        if not isinstance(item, dict):
            continue
        failure_id = str(item.get("id", "")).strip()
        assert failure_id
        assert str(item.get("meaning", "")).strip()
        assert str(item.get("severity", "")).strip()
        assert str(item.get("action", "")).strip()

    required_record = data.get("required_failure_record", [])
    assert isinstance(required_record, list)
    for field in {
        "failure_id",
        "failure_class",
        "stage",
        "input_entity_ids",
        "observed_behavior",
        "expected_behavior",
        "provenance_available",
        "scientific_impact",
        "remediation",
        "rerun_required",
    }:
        assert field in required_record

    rules = data.get("rules", [])
    assert isinstance(rules, list)
    assert any("software failure" in str(rule).lower() for rule in rules)
    assert any("insufficient evidence" in str(rule).lower() for rule in rules)

    print("H7 failure matrix audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
