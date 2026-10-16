"""G9.32 / AE-30 independent evaluation tests.

The evaluator is deliberately separate from the AE-29 unit-test helpers. These
tests assert the evaluator's independent acceptance report, its tamper-evident
digest, and its bounded scenario inventory.
"""
from __future__ import annotations

import copy
import json

import pytest

from audit_engine.semantic_audit.ae24.contracts import canonical, sha
from audit_engine.semantic_audit.ae30 import (
    REPORT_SCHEMA,
    run_evaluation,
    validate_evaluation_report,
)
from audit_engine.semantic_audit.ae29 import IterativeAuditError


def test_independent_evaluation_passes_all_reference_cases():
    report = run_evaluation()
    assert report["schema_version"] == REPORT_SCHEMA
    assert report["acceptance"]["status"] == "passed"
    assert report["metrics"]["total_cases"] == 14
    assert report["metrics"]["passed_cases"] == 14
    assert report["metrics"]["failed_cases"] == 0
    assert report["metrics"]["unauthorized_state_changes"] == 0
    assert report["metrics"]["replay_failures"] == 0
    assert report["metrics"]["memory_authorization_violations"] == 0
    assert validate_evaluation_report(report)["evaluation_sha256"] == report["evaluation_sha256"]


def test_independent_evaluation_has_expected_adversarial_coverage():
    report = run_evaluation()
    cases = {item["case_id"]: item for item in report["cases"]}
    expected = {
        "AE30-C06": "adversarial",
        "AE30-C07": "adversarial",
        "AE30-C08": "adversarial",
        "AE30-C09": "adversarial",
        "AE30-C14": "adversarial",
        "AE30-C10": "memory-boundary",
        "AE30-C12": "boundedness",
        "AE30-C13": "replay",
    }
    for case_id, class_name in expected.items():
        assert cases[case_id]["class_name"] == class_name
        assert cases[case_id]["passed"] is True


def test_evaluation_report_tampering_is_rejected():
    report = run_evaluation()
    tampered = copy.deepcopy(report)
    tampered["acceptance"]["status"] = "failed"
    with pytest.raises(IterativeAuditError, match="(digest|inconsistent)"):
        validate_evaluation_report(tampered)


def test_evaluation_report_case_tampering_is_rejected():
    report = run_evaluation()
    tampered = copy.deepcopy(report)
    tampered["cases"][0]["actual"] = "reject_repair"
    with pytest.raises(IterativeAuditError, match="digest"):
        validate_evaluation_report(tampered)


def test_evaluation_acceptance_requirements_are_immutable():
    report = run_evaluation()
    tampered = copy.deepcopy(report)
    tampered["acceptance"]["requirements"]["all_cases_pass"] = False
    with pytest.raises(IterativeAuditError, match="requirements"):
        validate_evaluation_report(tampered)


def test_evaluation_report_is_json_serializable():
    report = run_evaluation()
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"))
    assert json.loads(encoded)["evaluation_sha256"] == report["evaluation_sha256"]


def test_evaluation_report_rejects_self_consistent_but_inconsistent_metrics():
    report = run_evaluation()
    tampered = copy.deepcopy(report)
    tampered["metrics"]["unauthorized_state_changes"] = 1
    tampered["evaluation_sha256"] = sha(
        canonical({k: v for k, v in tampered.items() if k != "evaluation_sha256"})
    )
    with pytest.raises(IterativeAuditError, match="metric"):
        validate_evaluation_report(tampered)
