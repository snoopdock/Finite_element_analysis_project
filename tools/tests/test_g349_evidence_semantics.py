"""Adversarial evidence tests: re-hashing altered reports is NOT sufficient to pass."""
from __future__ import annotations

import argparse
import importlib.util
import json
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1]


def load(module_name):
    spec = importlib.util.spec_from_file_location(module_name, TOOLS / f"{module_name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load("validation_registry_runner")
verify = load("verify_validation_evidence")


class EvidenceSemanticTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / "source"
        self.evidence = self.root / "evidence"
        (self.repo / "validation/profiles").mkdir(parents=True)
        (self.repo / "tests").mkdir()
        (self.repo / "tests/test_example.py").write_text("def test_example():\n    assert True\n")
        (self.repo / "validation/schema.json").write_text(json.dumps(
            {"type": "object", "required": ["id", "name", "target_tests"]}))
        (self.repo / "validation/profiles/G3.4.9.yaml").write_text(
            "id: G3.4.9\nname: Evidence semantic tests\n"
            "target_tests:\n  - tests/test_example.py\nregression:\n  enabled: true\n  path: tests/\n")
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=Tests",
                        "-c", "user.email=tests@example.test", "commit", "-qm", "initial"], check=True)
        self.commit = subprocess.check_output(["git", "-C", str(self.repo), "rev-parse", "HEAD"], text=True).strip()
        self.engine_log = self.evidence / "engine-unit-tests.log"
        self.evidence.mkdir()
        self.engine_log.write_text("Ran 2 tests in 0.001s\n\nOK\n")

    def create(self, *, mode="profile", test_code=None):
        if test_code is not None:
            (self.repo / "tests/test_example.py").write_text(test_code)
        args = argparse.Namespace(repository=str(self.repo), profile="latest", evidence_dir=str(self.evidence),
                                  branch="stage1/section-uuids", regression_mode=mode,
                                  require_provenance=False, engine_unit_log=str(self.engine_log))
        return runner.run(args)

    def check(self, *, require_pass=True):
        return verify.verify(self.evidence, require_pass=require_pass, repository=self.repo,
                             expected_branch="stage1/section-uuids", require_engine_tests=True)

    def mutate(self, change, *, xml=False):
        report_file = self.evidence / "validation_report.json"
        report = json.loads(report_file.read_text())
        change(report)
        if xml:
            for stage in ("targeted", "regression"):
                result = report["results"].get(stage)
                if result and result.get("junit"):
                    path = self.evidence / result["junit"]["path"]
                    result["junit"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                    result["junit"]["size_bytes"] = path.stat().st_size
        report_file.write_bytes(runner.canonical_json(report))
        (self.evidence / "validation_report.sha256").write_text(
            runner.sha256_file(report_file) + "  validation_report.json\n")

    def test_positive_semantic_and_provenance_verification(self):
        self.assertEqual(self.create(), 0)
        doc = self.check()
        self.assertEqual(doc["schema_version"], "1.1")
        self.assertEqual(doc["target_commit_sha"], self.commit)
        self.assertEqual(doc["engine_unit_tests"]["count"], 2)
        self.assertEqual(doc["results"]["regression"]["status"], "passed")

    def test_rehashed_false_pass_rejected(self):
        self.assertEqual(self.create(), 0)
        self.mutate(lambda r: r["results"]["targeted"].update(exit_code=7))
        with self.assertRaisesRegex(ValueError, "zero exit code"):
            self.check()

    def test_rehashed_mismatched_counts_rejected(self):
        self.assertEqual(self.create(), 0)
        self.mutate(lambda r: r["results"]["targeted"]["counts"].update(tests=999))
        with self.assertRaisesRegex(ValueError, "counts disagree"):
            self.check()

    def test_rehashed_junit_failing_case_rejected(self):
        self.assertEqual(self.create(), 0)
        xml_file = self.evidence / "targeted.xml"
        xml = xml_file.read_text()
        xml_file.write_text(xml.replace('failures="0"', 'failures="1"'))
        self.mutate(lambda _: None, xml=True)
        with self.assertRaisesRegex(ValueError, "JUnit suite counts"):
            self.check()

    def test_rehashed_changed_targets_rejected(self):
        self.assertEqual(self.create(), 0)
        self.mutate(lambda r: r["results"]["targeted"]["argv"].__setitem__(2, "tests/other.py"))
        with self.assertRaisesRegex(ValueError, "Command does not match"):
            self.check()

    def test_rehashed_skipped_regression_rejected(self):
        self.assertEqual(self.create(), 0)
        self.mutate(lambda r: r["results"].__setitem__("regression", {"status": "not_run", "reason": "skip"}))
        with self.assertRaisesRegex(ValueError, "Regression execution contradicts"):
            self.check()

    def test_rehashed_wrong_commit_rejected(self):
        self.assertEqual(self.create(), 0)
        self.mutate(lambda r: r.__setitem__("target_commit_sha", "f" * 40))
        with self.assertRaisesRegex(ValueError, "target_commit_sha mismatch"):
            self.check()

    def test_uncommitted_profile_edit_rejected(self):
        self.assertEqual(self.create(), 0)
        with (self.repo / "validation/profiles/G3.4.9.yaml").open("a") as f:
            f.write("# drift\n")
        with self.assertRaisesRegex(ValueError, "Profile digest mismatch"):
            self.check()

    def test_report_branch_binding_rejected(self):
        self.assertEqual(self.create(), 0)
        with self.assertRaisesRegex(ValueError, "Target branch mismatch"):
            verify.verify(self.evidence, expected_branch="different")

    def test_report_run_binding_rejected(self):
        self.assertEqual(self.create(), 0)
        with self.assertRaisesRegex(ValueError, "GitHub run ID mismatch"):
            verify.verify(self.evidence, expected_run_id="12345")

    def test_engine_unit_log_corruption_rejected(self):
        self.assertEqual(self.create(), 0)
        self.engine_log.write_text("not OK\n")
        with self.assertRaisesRegex(ValueError, "Artifact (?:size|digest) mismatch"):
            self.check()

    def test_report_failing_test_is_accepted_but_not_pass(self):
        result = self.create(test_code="def test_example():\n    assert False\n")
        self.assertEqual(result, 1)
        doc = self.check(require_pass=False)
        self.assertEqual(doc["status"], "failed")
        with self.assertRaisesRegex(ValueError, "Tests did not pass"):
            self.check(require_pass=True)

    def test_all_skipped_tests_fail_policy(self):
        result = self.create(mode="skip", test_code="import pytest\n@pytest.mark.skip\ndef test_example():\n    pass\n")
        self.assertEqual(result, 1)
        doc = self.check(require_pass=False)
        self.assertEqual(doc["results"]["targeted"]["status"], "failed")

    def test_engine_log_mandatory_when_requested(self):
        self.assertEqual(self.create(), 0)
        self.mutate(lambda r: r.__setitem__("engine_unit_tests", None))
        with self.assertRaisesRegex(ValueError, "Missing engine unit-test"):
            self.check()


if __name__ == "__main__":
    unittest.main()
