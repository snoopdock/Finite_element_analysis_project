from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "tools" / "verify_ae32c_batch_acceptance.py"
spec = importlib.util.spec_from_file_location("verify_ae32c_batch_acceptance", HELPER)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def valid_summary(rounds: int = 4) -> dict:
    n = rounds * 3
    return {
        "schema_version": "ae32c/batch-evaluation/v3",
        "expected_trials": n,
        "observed_trials": n,
        "baseline_completed": n,
        "graph_protocol_completed": n,
        "graph_evidence_complete": n,
        "overall_accepted_trials": n,
        "passed": True,
    }


def test_v3_summary_passes_only_when_all_trials_pass_every_gate():
    result = module.validate_batch_summary(valid_summary(), 4)
    assert result["overall_accepted_trials"] == 12
    assert result["graph_evidence_complete"] == 12


def test_v3_does_not_read_ambiguous_legacy_evidence_complete_key():
    summary = valid_summary(1)
    summary["evidence_complete"] = 0  # deliberately stale/ambiguous alias
    assert module.validate_batch_summary(summary, 1)["overall_accepted_trials"] == 3


def test_partial_overall_acceptance_fails_closed():
    summary = valid_summary(4)
    summary["overall_accepted_trials"] = 11
    summary["passed"] = False
    try:
        module.validate_batch_summary(summary, 4)
    except module.BatchAcceptanceError as exc:
        assert "Overall acceptance passed for 11 of 12" in str(exc)
    else:
        raise AssertionError("partial acceptance must fail")


def test_partial_graph_evidence_fails_closed_even_if_pass_flag_is_true():
    summary = valid_summary(1)
    summary["graph_evidence_complete"] = 2
    try:
        module.validate_batch_summary(summary, 1)
    except module.BatchAcceptanceError as exc:
        assert "Graph evidence complete for 2 of 3" in str(exc)
    else:
        raise AssertionError("incomplete graph evidence must fail")


def test_latest_observed_6_of_12_batch_remains_rejected():
    summary = {
        "schema_version": "ae32c/batch-evaluation/v3",
        "expected_trials": 12,
        "observed_trials": 12,
        "baseline_completed": 11,
        "graph_protocol_completed": 6,
        "graph_evidence_complete": 6,
        "overall_accepted_trials": 6,
        "passed": False,
    }
    try:
        module.validate_batch_summary(summary, 4)
    except module.BatchAcceptanceError as exc:
        assert "Baseline completed for 11 of 12" in str(exc)
    else:
        raise AssertionError("the latest 6/12 run must remain rejected")


def test_v2_or_missing_schema_is_rejected():
    summary = valid_summary(1)
    summary["schema_version"] = "ae32c/batch-evaluation/v2"
    try:
        module.validate_batch_summary(summary, 1)
    except module.BatchAcceptanceError as exc:
        assert "ae32c/batch-evaluation/v3" in str(exc)
    else:
        raise AssertionError("legacy schema must fail")


def test_boolean_is_not_accepted_as_integer_count():
    summary = valid_summary(1)
    summary["observed_trials"] = True
    try:
        module.validate_batch_summary(summary, 1)
    except module.BatchAcceptanceError as exc:
        assert "observed_trials" in str(exc)
    else:
        raise AssertionError("boolean count must fail")
