from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.ae32c_source_snapshot_manifest import (
    SCHEMA, SnapshotError, capture_manifest, verify_manifest,
)


class SourceSnapshotManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self._git("init", "-q")
        self._git("config", "user.email", "snapshot-test@example.invalid")
        self._git("config", "user.name", "Snapshot Test")
        (self.root / "module.py").write_text("VALUE = 7\n", encoding="utf-8")
        (self.root / "nested").mkdir()
        (self.root / "nested" / "data.txt").write_bytes(b"source-data\x00bytes")
        self._git("add", ".")
        self._git("commit", "-qm", "initial fixture")
        self.commit = self._git("rev-parse", "HEAD")

    def tearDown(self):
        self.temp.cleanup()

    def _git(self, *args):
        result = subprocess.run(["git", *args], cwd=self.root,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return result.stdout.decode("utf-8").strip()

    def _capture(self):
        return capture_manifest(
            self.root, expected_source_revision=self.commit, event_name="push",
            repository_name="example/repository", ref="refs/heads/test")

    def test_capture_binds_commit_tree_inventory_and_blob_content(self):
        manifest = self._capture()
        self.assertEqual(manifest["manifest_schema"], SCHEMA)
        self.assertEqual(manifest["source"]["commit_oid"], self.commit)
        self.assertEqual(manifest["source"]["root_tree_oid"],
                         self._git("rev-parse", "HEAD^{tree}"))
        self.assertEqual(manifest["source"]["commit_oid_algorithm"], "sha1")
        entries = manifest["source_inventory"]["entries"]
        item = next(row for row in entries if row["path"] == "nested/data.txt")
        self.assertEqual(item["content_sha256"],
                         hashlib.sha256(b"source-data\x00bytes").hexdigest())
        expected = hashlib.sha256(
            (json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
             + "\n").encode("utf-8")).hexdigest()
        self.assertEqual(manifest["source_inventory"]["sha256"], expected)
        self.assertEqual(manifest["status"], "CAPTURED_PENDING_POSTFLIGHT")
        self.assertFalse(manifest["authority"]["atomic_repository_snapshot_established"])

    def test_unchanged_source_passes_postflight(self):
        manifest = self._capture()
        path = self.root.parent / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        result = verify_manifest(self.root, path, expected_source_revision=self.commit)
        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(result["verification"]["status"], "VERIFIED")
        self.assertTrue(result["verification"]["worktree_clean_at_verification"])

    def test_tracked_mutation_fails_postflight_and_is_recorded(self):
        manifest = self._capture()
        path = self.root.parent / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        (self.root / "module.py").write_text("VALUE = 8\n", encoding="utf-8")
        with self.assertRaisesRegex(SnapshotError, "worktree_not_clean"):
            verify_manifest(self.root, path, expected_source_revision=self.commit)
        failed = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(failed["status"], "FAILED")
        self.assertEqual(failed["verification"]["status"], "FAILED")

    def test_untracked_file_fails_postflight(self):
        manifest = self._capture()
        path = self.root.parent / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        (self.root / "untracked.txt").write_text("unexpected", encoding="utf-8")
        with self.assertRaisesRegex(SnapshotError, "worktree_not_clean"):
            verify_manifest(self.root, path, expected_source_revision=self.commit)

    def test_expected_commit_mismatch_is_rejected(self):
        with self.assertRaisesRegex(SnapshotError, "does_not_match_expected"):
            capture_manifest(self.root, expected_source_revision="0" * len(self.commit),
                             event_name="push", repository_name="example/repository")

    def test_pull_request_context_records_base_and_head(self):
        event_path = self.root.parent / "event.json"
        event_path.write_text(json.dumps({"pull_request": {
            "base": {"sha": "a" * 40}, "head": {"sha": "b" * 40},
            "merge_commit_sha": self.commit}}), encoding="utf-8")
        manifest = capture_manifest(
            self.root, expected_source_revision=self.commit, event_name="pull_request",
            repository_name="example/repository", ref="refs/pull/3/merge",
            event_path=event_path)
        self.assertEqual(manifest["source"]["source_mode"], "pull_request_merge")
        self.assertEqual(manifest["source"]["base_commit_oid"], "a" * 40)
        self.assertEqual(manifest["source"]["head_commit_oid"], "b" * 40)
        self.assertEqual(manifest["source"]["commit_oid"], self.commit)

    def test_capture_rejects_dirty_worktree(self):
        (self.root / "module.py").write_text("dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(SnapshotError, "worktree_not_clean_at_capture"):
            self._capture()


if __name__ == "__main__":
    unittest.main()
