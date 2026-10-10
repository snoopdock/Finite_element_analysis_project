"""G3.4.10 adversarial tests for immutable evidence bundle publication."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import sys
import subprocess
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile, ZipInfo, ZIP_STORED

from audit_engine.semantic_audit.high_assurance.validation_evidence_store import (
    EvidenceBundleError, EvidenceBundleStore, inspect_bundle,
)


def h(content):
    return hashlib.sha256(content).hexdigest()


def canonical(data):
    return (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()


class EvidenceBundleTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)
        self.source = self.root / "evidence"
        self.source.mkdir()
        self.store = EvidenceBundleStore(self.root / "store")
        self._fixture()

    def _fixture(self, *, status="passed", regression_failure=False):
        junit = b'<testsuite tests="2" failures="0" errors="0" skipped="0"><testcase name="one"/><testcase name="two"/></testsuite>'
        reg = (b'<testsuite tests="2" failures="1" errors="0" skipped="0"><testcase name="one"><failure/></testcase><testcase name="two"/></testsuite>'
               if regression_failure else junit)
        files = {
            "targeted.log": b"2 passed\n",
            "targeted.xml": junit,
            "regression.log": b"one failure\n" if regression_failure else b"2 passed\n",
            "regression.xml": reg,
            "engine-unit-tests.log": b"24 tests passed\n",
        }
        for name, content in files.items():
            (self.source / name).write_bytes(content)
        def rec(name):
            return {"path": name, "sha256": h(files[name]), "size_bytes": len(files[name])}
        report = {
            "schema_version": "1.1", "status": status,
            "profile_id": "G3.4.9", "target_commit_sha": "1" * 40,
            "engine_commit_sha": "2" * 40,
            "engine_unit_tests": {"count": 24, "status": "passed", "log": rec("engine-unit-tests.log")},
            "results": {
                "targeted": {"status": "passed", "exit_code": 0, "counts": {"tests": 2, "failures": 0, "errors": 0, "skipped": 0},
                             "log": rec("targeted.log"), "junit": rec("targeted.xml")},
                "regression": {"status": "failed" if regression_failure else "passed", "exit_code": 1 if regression_failure else 0,
                               "counts": {"tests": 2, "failures": 1 if regression_failure else 0, "errors": 0, "skipped": 0},
                               "log": rec("regression.log"), "junit": rec("regression.xml")},
            },
        }
        blob = canonical(report)
        (self.source / "validation_report.json").write_bytes(blob)
        (self.source / "validation_report.sha256").write_text(f"{h(blob)}  validation_report.json\n")
        return report

    def _replace_report(self, edit):
        report = json.loads((self.source / "validation_report.json").read_text())
        edit(report)
        blob = canonical(report)
        (self.source / "validation_report.json").write_bytes(blob)
        (self.source / "validation_report.sha256").write_text(f"{h(blob)}  validation_report.json\n")

    def test_manual_dispatch_bundle_cli_generates_downloadable_files(self):
        repository = Path(__file__).resolve().parents[2]
        command = [sys.executable, str(repository / "tools/publish_validation_evidence_bundle.py"),
                   "--evidence-dir", str(self.source),
                   "--store-dir", str(self.root / "cli-store")]
        environment = dict(os.environ, PYTHONPATH=str(repository))
        process = subprocess.run(command, cwd=repository, env=environment,
                                 text=True, capture_output=True, check=False)
        self.assertEqual(process.returncode, 0, process.stderr)
        receipt = json.loads((self.source / "bundle_receipt.json").read_text())
        self.assertEqual(receipt["schema_version"], "validation-evidence-cas-receipt/v1")
        bundle = self.source / "bundles" / (receipt["bundle_sha256"] + ".validation.zip")
        self.assertTrue(bundle.is_file())
        self.assertEqual(inspect_bundle(bundle.read_bytes()),
                         (receipt["bundle_sha256"], receipt["report_sha256"]))

    def test_publish_verify_and_idempotent(self):
        first = self.store.publish(self.source)
        self.assertTrue(first.committed)
        self.assertFalse(self.store.publish(self.source).committed)
        self.assertEqual(self.store.verify(first.bundle_sha256).report_sha256, first.report_sha256)
        self.assertEqual(len(list((self.root / "store").glob("*.validation.zip"))), 1)

    def test_deterministic_across_distinct_roots(self):
        receipt = self.store.publish(self.source)
        other = EvidenceBundleStore(self.root / "other")
        self.assertEqual(other.publish(self.source).bundle_sha256, receipt.bundle_sha256)

    def test_source_files_unchanged(self):
        prior = {p.name: p.read_bytes() for p in self.source.iterdir()}
        self.store.publish(self.source)
        self.assertEqual(prior, {p.name: p.read_bytes() for p in self.source.iterdir()})

    def test_missing_member_rejected(self):
        (self.source / "targeted.log").unlink()
        with self.assertRaises(EvidenceBundleError):
            self.store.publish(self.source)

    def test_corrupt_log_rejected(self):
        (self.source / "targeted.log").write_bytes(b"tampered")
        with self.assertRaises(EvidenceBundleError):
            self.store.publish(self.source)

    def test_bad_detached_hash_rejected(self):
        (self.source / "validation_report.sha256").write_text("0" * 64 + "  validation_report.json\n")
        with self.assertRaises(EvidenceBundleError):
            self.store.publish(self.source)

    def test_undeclared_member_rejected(self):
        (self.source / "extra.txt").write_text("unregistered")
        with self.assertRaises(EvidenceBundleError):
            self.store.publish(self.source)

    def test_symlink_member_rejected(self):
        (self.source / "targeted.log").unlink()
        (self.source / "targeted.log").symlink_to(self.source / "regression.log")
        with self.assertRaises(EvidenceBundleError):
            self.store.publish(self.source)

    def test_symlink_store_rejected(self):
        (self.root / "alias").symlink_to(self.root / "store", target_is_directory=True)
        with self.assertRaises(EvidenceBundleError):
            EvidenceBundleStore(self.root / "alias")

    def test_report_status_unknown_rejected(self):
        self._replace_report(lambda r: r.update(status="unknown"))
        with self.assertRaises(EvidenceBundleError):
            self.store.publish(self.source)

    def test_invalid_commit_rejected(self):
        self._replace_report(lambda r: r.update(engine_commit_sha="bad"))
        with self.assertRaises(EvidenceBundleError):
            self.store.publish(self.source)

    def test_junit_count_mismatch_rejected_even_with_new_report_hash(self):
        self._replace_report(lambda r: r["results"]["targeted"]["counts"].update(tests=999))
        with self.assertRaises(EvidenceBundleError):
            self.store.publish(self.source)

    def test_claim_pass_when_junit_failure_rejected(self):
        def edit(r):
            r["results"]["targeted"]["exit_code"] = 1
        self._replace_report(edit)
        with self.assertRaises(EvidenceBundleError):
            self.store.publish(self.source)

    def test_overall_pass_cannot_contradict_regression_failure(self):
        self._fixture(status="passed", regression_failure=True)
        with self.assertRaises(EvidenceBundleError):
            self.store.publish(self.source)

    def test_outcome_failure_is_preservable_for_diagnostics(self):
        self._fixture(status="failed", regression_failure=True)
        receipt = self.store.publish(self.source)
        self.assertEqual(self.store.verify(receipt.bundle_sha256).report_sha256, receipt.report_sha256)

    def test_preexisting_corruption_never_overwritten(self):
        receipt = self.store.publish(self.source)
        target = self.store._target(receipt.bundle_sha256)
        target.write_bytes(b"corrupt")
        with self.assertRaises(EvidenceBundleError):
            self.store.publish(self.source)
        self.assertEqual(target.read_bytes(), b"corrupt")

    def test_preexisting_symlink_never_followed(self):
        receipt = self.store.publish(self.source)
        target = self.store._target(receipt.bundle_sha256)
        target.unlink()
        other = self.root / "outside"
        other.write_bytes(b"untouched")
        target.symlink_to(other)
        with self.assertRaises(EvidenceBundleError):
            self.store.publish(self.source)
        self.assertEqual(other.read_bytes(), b"untouched")

    def test_simultaneous_writers_single_commit(self):
        with ThreadPoolExecutor(max_workers=6) as executor:
            receipts = list(executor.map(lambda _: self.store.publish(self.source), range(12)))
        self.assertEqual(sum(r.committed for r in receipts), 1)
        self.assertEqual(len({r.bundle_sha256 for r in receipts}), 1)

    def test_invalid_digest_rejected(self):
        with self.assertRaises(EvidenceBundleError):
            self.store.verify("../../etc/passwd")

    def test_tampered_bundle_rejected(self):
        receipt = self.store.publish(self.source)
        p = self.store._target(receipt.bundle_sha256)
        blob = p.read_bytes()
        p.write_bytes(blob[:-1] + bytes([blob[-1] ^ 1]))
        with self.assertRaises(EvidenceBundleError):
            self.store.verify(receipt.bundle_sha256)

    def test_zip_traversal_rejected(self):
        from io import BytesIO
        out = BytesIO()
        with ZipFile(out, "w") as z:
            z.writestr("../escaped.txt", "hello")
            z.writestr("bundle_manifest.json", "{}")
            z.writestr("validation_report.json", "{}")
        with self.assertRaises(EvidenceBundleError):
            inspect_bundle(out.getvalue())

    def test_different_evidence_creates_distinct_bundles(self):
        a = self.store.publish(self.source)
        self._replace_report(lambda r: r.update(github_run_id="38041910716"))
        b = self.store.publish(self.source)
        self.assertNotEqual(a.bundle_sha256, b.bundle_sha256)
        self.assertTrue(b.committed)

    def test_manifest_lists_all_inputs(self):
        receipt = self.store.publish(self.source)
        with ZipFile(self.store._target(receipt.bundle_sha256)) as archive:
            manifest = json.loads(archive.read("bundle_manifest.json"))
            self.assertEqual(manifest["schema_version"], "validation-evidence-cas/v1")
            self.assertEqual(len(manifest["files"]), 7)
            self.assertEqual(manifest["report_sha256"], receipt.report_sha256)


if __name__ == "__main__":
    unittest.main()
