from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "tools" / "verify_ae32c_batch_acceptance.py"
spec = importlib.util.spec_from_file_location("verify_ae32c_batch_acceptance", HELPER)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

PROVIDERS = ("cloudflare", "nararouter", "openrouter")
METRICS = (
    "baseline_completed",
    "graph_protocol_completed",
    "graph_evidence_complete",
    "overall_accepted_trials",
)


def valid_summary(rounds: int = 4) -> dict:
    n = rounds * len(PROVIDERS)
    row = {
        "trials": rounds,
        "baseline_completed": rounds,
        "graph_protocol_completed": rounds,
        "graph_evidence_complete": rounds,
        "overall_accepted_trials": rounds,
    }
    return {
        "schema_version": "ae32c/batch-evaluation/v3",
        "expected_trials": n,
        "observed_trials": n,
        "baseline_completed": n,
        "graph_protocol_completed": n,
        "graph_evidence_complete": n,
        "overall_accepted_trials": n,
        "provider_breakdown": {provider: dict(row) for provider in PROVIDERS},
        "passed": True,
    }


def test_v3_summary_passes_only_when_all_trials_pass_every_gate():
    result = module.validate_batch_summary(valid_summary(), 4)
    assert result["overall_accepted_trials"] == 12
    assert result["graph_evidence_complete"] == 12


def test_v3_does_not_read_ambiguous_legacy_evidence_complete_key():
    summary = valid_summary(1)
    summary["evidence_complete"] = 0
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


def test_actual_5_of_12_batch_from_run_41107823092_is_rejected():
    row = {
        "cloudflare": {
            "trials": 4, "baseline_completed": 4, "graph_protocol_completed": 3,
            "graph_evidence_complete": 3, "overall_accepted_trials": 3,
        },
        "nararouter": {
            "trials": 4, "baseline_completed": 4, "graph_protocol_completed": 2,
            "graph_evidence_complete": 2, "overall_accepted_trials": 2,
        },
        "openrouter": {
            "trials": 4, "baseline_completed": 0, "graph_protocol_completed": 0,
            "graph_evidence_complete": 0, "overall_accepted_trials": 0,
        },
    }
    summary = {
        "schema_version": "ae32c/batch-evaluation/v3",
        "expected_trials": 12,
        "observed_trials": 12,
        "baseline_completed": 8,
        "graph_protocol_completed": 5,
        "graph_evidence_complete": 5,
        "overall_accepted_trials": 5,
        "provider_breakdown": row,
        "passed": False,
    }
    try:
        module.validate_batch_summary(summary, 4)
    except module.BatchAcceptanceError as exc:
        assert "Baseline completed for 8 of 12" in str(exc)
    else:
        raise AssertionError("the observed 5/12 batch must remain rejected")


def test_missing_trial_is_rejected_even_if_other_counts_claim_success():
    summary = valid_summary(4)
    summary["observed_trials"] = 11
    try:
        module.validate_batch_summary(summary, 4)
    except module.BatchAcceptanceError as exc:
        assert "Observed 11 of 12 expected trials" in str(exc)
    else:
        raise AssertionError("a batch with a missing trial must fail closed")


def test_dispatch_denominator_mismatch_is_rejected():
    summary = valid_summary(4)
    summary["expected_trials"] = 9
    try:
        module.validate_batch_summary(summary, 4)
    except module.BatchAcceptanceError as exc:
        assert "Expected-trial denominator mismatch" in str(exc)
    else:
        raise AssertionError("a denominator inconsistent with dispatch must fail")


def test_provider_breakdown_must_match_all_three_dispatched_providers():
    summary = valid_summary(1)
    del summary["provider_breakdown"]["openrouter"]
    try:
        module.validate_batch_summary(summary, 1)
    except module.BatchAcceptanceError as exc:
        assert "Provider breakdown mismatch" in str(exc)
    else:
        raise AssertionError("missing provider breakdown must fail")


def test_each_provider_must_pass_each_metric_for_every_round():
    summary = valid_summary(4)
    summary["provider_breakdown"]["cloudflare"]["graph_evidence_complete"] = 3
    try:
        module.validate_batch_summary(summary, 4)
    except module.BatchAcceptanceError as exc:
        assert "cloudflare graph_evidence_complete passed for 3 of 4" in str(exc)
    else:
        raise AssertionError("provider-level evidence deficit must fail")


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
