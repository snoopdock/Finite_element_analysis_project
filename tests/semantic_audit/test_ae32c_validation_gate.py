from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from audit_engine.semantic_audit.ae32c.validation_gate import (
    ValidationGateError,
    validate_report_binding,
    validate_run_metadata,
)


SOURCE_SHA = "a" * 40
ENGINE_SHA = "b" * 40
RUN_ID = "39843574421"
PROFILE_SHA = "c" * 64


def metadata(**overrides):
    value = {
        "id": int(RUN_ID),
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "head_branch": "main",
        "path": ".github/workflows/00_manual_validation_dispatcher.yml@refs/heads/main",
        "head_sha": ENGINE_SHA,
        "run_attempt": 1,
        "head_repository": {"full_name": "snoopdock/Finite_element_analysis_project"},
    }
    value.update(overrides)
    return value


def report_record(**overrides):
    value = {
        "schema_version": "1.1",
        "status": "passed",
        "error": None,
        "requested_profile": "G9.42",
        "profile_id": "G9.42",
        "profile_sha256": PROFILE_SHA,
        "target_branch": "stage1/section-uuids",
        "target_commit_sha": SOURCE_SHA,
        "engine_commit_sha": ENGINE_SHA,
        "github_run_id": RUN_ID,
        "github_run_attempt": "1",
        "engine_unit_tests": {"status": "passed", "count": 43},
        "results": {
            "targeted": {
                "status": "passed", "exit_code": 0,
                "counts": {"tests": 161, "failures": 0, "errors": 0, "skipped": 0},
            },
            "regression": {
                "status": "passed", "exit_code": 0,
                "counts": {"tests": 3127, "failures": 0, "errors": 0, "skipped": 8},
            },
        },
    }
    value.update(overrides)
    return value


def write_evidence(root: Path, report: dict | None = None, *, catalog_overrides=None):
    root.mkdir(parents=True, exist_ok=True)
    (root / "catalog").mkdir(exist_ok=True)
    raw = json.dumps(report or report_record(), sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(raw).hexdigest()
    (root / "validation_report.json").write_bytes(raw)
    (root / "validation_report.sha256").write_text(f"{digest}  validation_report.json\n")
    bundle_sha = "d" * 64
    catalog = {
        "status": "passed",
        "regression_status": "passed",
        "profile_id": "G9.42",
        "branch": "stage1/section-uuids",
        "source_commit_sha": SOURCE_SHA,
        "engine_commit_sha": ENGINE_SHA,
        "github_run_id": RUN_ID,
        "github_run_attempt": "1",
        "report_sha256": digest,
        "bundle_sha256": bundle_sha,
        "bundle_size_bytes": 123,
    }
    catalog.update(catalog_overrides or {})
    (root / "catalog" / "catalog_entry.json").write_text(json.dumps(catalog))
    receipt = {
        "bundle_sha256": bundle_sha,
        "byte_size": 123,
        "report_sha256": digest,
        "source_commit_sha": SOURCE_SHA,
        "engine_commit_sha": ENGINE_SHA,
        "github_run_id": RUN_ID,
        "github_run_attempt": "1",
    }
    receipt_bytes = json.dumps(receipt).encode()
    (root / "bundle_receipt.json").write_bytes(receipt_bytes)
    (root / "bundle_receipt.sha256").write_text(
        f"{hashlib.sha256(receipt_bytes).hexdigest()}  bundle_receipt.json\n"
    )
    return digest


class ValidationRunMetadataTests(unittest.TestCase):
    def test_accepts_only_successful_manual_dispatcher_run_from_main(self):
        result = validate_run_metadata(
            metadata(), expected_run_id=RUN_ID,
            expected_repository="snoopdock/Finite_element_analysis_project",
        )
        self.assertEqual(result["run_attempt"], "1")
        self.assertEqual(result["engine_commit_sha"], ENGINE_SHA)

    def test_rejects_failed_validation_run(self):
        with self.assertRaisesRegex(ValidationGateError, "validation_run_not_successful"):
            validate_run_metadata(metadata(conclusion="failure"), expected_run_id=RUN_ID)

    def test_rejects_in_progress_run(self):
        with self.assertRaisesRegex(ValidationGateError, "validation_run_not_completed"):
            validate_run_metadata(metadata(status="in_progress", conclusion=None), expected_run_id=RUN_ID)

    def test_rejects_wrong_workflow_path(self):
        with self.assertRaisesRegex(ValidationGateError, "unexpected_validation_workflow"):
            validate_run_metadata(metadata(path=".github/workflows/ae32c-live-evaluation.yml@refs/heads/main"),
                                  expected_run_id=RUN_ID)

    def test_rejects_non_manual_event(self):
        with self.assertRaisesRegex(ValidationGateError, "validation_run_not_manual"):
            validate_run_metadata(metadata(event="push"), expected_run_id=RUN_ID)

    def test_rejects_run_from_development_branch(self):
        with self.assertRaisesRegex(ValidationGateError, "validation_workflow_not_from_main"):
            validate_run_metadata(metadata(head_branch="stage1/section-uuids"), expected_run_id=RUN_ID)

    def test_rejects_wrong_repository(self):
        with self.assertRaisesRegex(ValidationGateError, "validation_run_repository_mismatch"):
            validate_run_metadata(metadata(), expected_run_id=RUN_ID, expected_repository="attacker/fork")

    def test_rejects_non_numeric_run_id(self):
        with self.assertRaisesRegex(ValidationGateError, "invalid_validation_run_id"):
            validate_run_metadata(metadata(), expected_run_id="../latest")


class ValidationReportBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        write_evidence(self.root)
        self.binding = validate_run_metadata(
            metadata(), expected_run_id=RUN_ID,
            expected_repository="snoopdock/Finite_element_analysis_project",
        )

    def tearDown(self):
        self.temp.cleanup()

    def verify(self, **kwargs):
        return validate_report_binding(
            self.root,
            run_metadata=self.binding,
            expected_run_id=RUN_ID,
            expected_source_commit=SOURCE_SHA,
            expected_profile_sha256=PROFILE_SHA,
            **kwargs,
        )

    def test_accepts_exact_passed_g942_record(self):
        result = self.verify()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["validation_profile"], "G9.42")
        self.assertEqual(result["source_commit_sha"], SOURCE_SHA)
        self.assertEqual(result["targeted_tests"], 161)
        self.assertEqual(result["regression_skipped"], 8)

    def test_rejects_report_digest_tampering(self):
        (self.root / "validation_report.json").write_text("{}")
        with self.assertRaisesRegex(ValidationGateError, "validation_report_digest_mismatch"):
            self.verify()

    def test_rejects_failed_report_even_when_digest_is_valid(self):
        write_evidence(self.root, report_record(status="failed"))
        with self.assertRaisesRegex(ValidationGateError, "validation_report_not_passed"):
            self.verify()

    def test_rejects_other_profile(self):
        write_evidence(self.root, report_record(profile_id="G9.41", requested_profile="G9.41"))
        with self.assertRaisesRegex(ValidationGateError, "validation_profile_not_g942"):
            self.verify()

    def test_rejects_other_source_commit(self):
        write_evidence(self.root, report_record(target_commit_sha="e" * 40))
        with self.assertRaisesRegex(ValidationGateError, "validation_source_commit_mismatch"):
            self.verify()

    def test_rejects_other_engine_commit(self):
        write_evidence(self.root, report_record(engine_commit_sha="f" * 40))
        with self.assertRaisesRegex(ValidationGateError, "validation_engine_commit_mismatch"):
            self.verify()

    def test_rejects_report_from_other_run_attempt(self):
        write_evidence(self.root, report_record(github_run_attempt="2"))
        with self.assertRaisesRegex(ValidationGateError, "validation_report_attempt_mismatch"):
            self.verify()

    def test_rejects_targeted_failures(self):
        write_evidence(self.root, report_record(results={
            "targeted": {"status": "passed", "exit_code": 0,
                         "counts": {"tests": 10, "failures": 1, "errors": 0, "skipped": 0}},
            "regression": {"status": "passed", "exit_code": 0,
                           "counts": {"tests": 20, "failures": 0, "errors": 0, "skipped": 0}},
        }))
        with self.assertRaisesRegex(ValidationGateError, "targeted_failures_present"):
            self.verify()

    def test_rejects_all_skipped_regression(self):
        write_evidence(self.root, report_record(results={
            "targeted": {"status": "passed", "exit_code": 0,
                         "counts": {"tests": 10, "failures": 0, "errors": 0, "skipped": 0}},
            "regression": {"status": "passed", "exit_code": 0,
                           "counts": {"tests": 20, "failures": 0, "errors": 0, "skipped": 20}},
        }))
        with self.assertRaisesRegex(ValidationGateError, "regression_invalid_skips"):
            self.verify()

    def test_rejects_catalog_source_binding_mismatch(self):
        write_evidence(self.root, catalog_overrides={"source_commit_sha": "e" * 40})
        with self.assertRaisesRegex(ValidationGateError, "validation_catalog_source_commit_mismatch"):
            self.verify()

    def test_rejects_bundle_receipt_mismatch(self):
        write_evidence(self.root)
        (self.root / "bundle_receipt.json").write_text(json.dumps({"bundle_sha256": "wrong"}))
        with self.assertRaisesRegex(ValidationGateError, "validation_bundle_receipt_digest_mismatch"):
            self.verify()

    def test_rejects_symlinked_report(self):
        report = self.root / "validation_report.json"
        raw = report.read_bytes()
        report.unlink()
        outside = self.root.parent / (self.root.name + "-outside.json")
        outside.write_bytes(raw)
        report.symlink_to(outside)
        try:
            with self.assertRaisesRegex(ValidationGateError, "missing_or_unsafe_evidence_file"):
                self.verify()
        finally:
            outside.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
