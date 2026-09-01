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
    failures = data.get("failures", data.get("failure_modes", []))
    assert isinstance(failures, list)
    codes = {str(item.get("code", "")).strip() for item in failures if isinstance(item, dict)}
    missing = REQUIRED_CODES - codes
    assert not missing, f"Missing H7 failure codes: {sorted(missing)}"

    for item in failures:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code", "")).strip()
        assert code
        assert str(item.get("category", "")).strip()
        assert str(item.get("description", "")).strip()
        assert str(item.get("expected_behavior", "")).strip()

    print("H7 failure matrix audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
