"""Trusted engine regression tests; executed before running target-branch tests."""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1]


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load("validation_registry_runner")
verifier = load("verify_validation_evidence")


class RegistryEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        (self.repo / "validation/profiles").mkdir(parents=True)
        (self.repo / "tests").mkdir()
        (self.repo / "validation/schema.json").write_text(
            json.dumps({"type": "object", "required": ["id", "name", "target_tests"]}))
        (self.repo / "tests/test_example.py").write_text("def test_example():\n    assert True\n")
        self.profile("G3.4.7.4")
        self.profile("G3.4.8")

    def tearDown(self):
        self.tmp.cleanup()

    def profile(self, name, target="tests/test_example.py", regression=False):
        (self.repo / f"validation/profiles/{name}.yaml").write_text(
            f"id: {name}\nname: Example\ntarget_tests:\n  - {target}\n"
            f"regression:\n  enabled: {'true' if regression else 'false'}\n  path: tests/\n")

    def args(self, **kw):
        return argparse.Namespace(repository=str(self.repo), profile="latest",
                                  evidence_dir=str(self.root / "evidence"),
                                  branch="stage1/section-uuids", regression_mode="skip",
                                  require_provenance=False, **kw)

    def test_latest_uses_numeric_versions_not_lexical_order(self):
        self.profile("G3.4.10")
        self.assertEqual(runner.discover_profile(self.repo, "latest").stem, "G3.4.10")

    def test_rejects_profile_traversal_and_missing_profiles(self):
        for bad in ("../../secrets", "G3.4.99", "G3.4.8/../../secret"):
            with self.assertRaises(ValueError):
                runner.discover_profile(self.repo, bad)

    def test_rejects_missing_target(self):
        self.profile("G3.4.8", "tests/not_existing.py")
        with self.assertRaises(ValueError):
            runner.load_profile(self.repo, runner.discover_profile(self.repo, "latest"))

    def test_rejects_escape_path(self):
        self.profile("G3.4.8", "tests/../../escape.py")
        with self.assertRaises(ValueError):
            runner.load_profile(self.repo, runner.discover_profile(self.repo, "latest"))

    def test_rejects_symlinked_target(self):
        (self.repo / "tests/linked.py").symlink_to("test_example.py")
        self.profile("G3.4.8", "tests/linked.py")
        with self.assertRaises(ValueError):
            runner.load_profile(self.repo, runner.discover_profile(self.repo, "latest"))

    def test_real_passed_pytest_produces_verified_artifact(self):
        code = runner.run(self.args())
        self.assertEqual(code, 0)
        out = self.root / "evidence"
        doc = verifier.verify(out, require_pass=True)
        self.assertEqual(doc["status"], "passed")
        self.assertEqual(doc["profile_id"], "G3.4.8")
        self.assertEqual(doc["results"]["targeted"]["status"], "passed")
        self.assertEqual(doc["results"]["targeted"]["counts"]["tests"], 1)
        self.assertEqual(doc["results"]["regression"]["status"], "not_run")

    def test_real_failing_pytest_marks_report_failed(self):
        (self.repo / "tests/test_example.py").write_text("def test_example():\n    assert False\n")
        self.assertEqual(runner.run(self.args()), 1)
        out = self.root / "evidence"
        report = verifier.verify(out)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["results"]["targeted"]["status"], "failed")
        with self.assertRaises(ValueError):
            verifier.verify(out, require_pass=True)

    def test_report_tampering_is_rejected(self):
        self.assertEqual(runner.run(self.args()), 0)
        artifact = self.root / "evidence" / "validation_report.json"
        artifact.write_bytes(artifact.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            verifier.verify(self.root / "evidence")

    def test_log_tampering_is_rejected(self):
        self.assertEqual(runner.run(self.args()), 0)
        log = self.root / "evidence" / "targeted.log"
        log.write_text("tampered", encoding="utf-8")
        with self.assertRaises(ValueError):
            verifier.verify(self.root / "evidence")

    def test_invalid_profile_fails_and_still_emits_error_report(self):
        self.profile("G3.4.8", "tests/unknown_file.py")
        self.assertEqual(runner.run(self.args()), 1)
        report = verifier.verify(self.root / "evidence")
        self.assertEqual(report["status"], "error")
        self.assertEqual(report["results"], {})


if __name__ == "__main__":
    unittest.main()
