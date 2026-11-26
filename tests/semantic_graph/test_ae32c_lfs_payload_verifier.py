from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from audit_engine.semantic_audit.ae32c.git_object_source import GitObjectSourceProvider
from audit_engine.semantic_audit.ae32c.lfs_payload_verifier import (
    LfsPayloadVerificationError, parse_lfs_pointer, verify_lfs_payloads,
)
from tools.ae32c_source_snapshot_manifest import capture_manifest, verify_manifest


class LfsPayloadVerifierTests(unittest.TestCase):
    def _git(self, root: Path, *args: str) -> str:
        result = subprocess.run(["git", *args], cwd=root, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return result.stdout.strip()

    def _provider(self, root: Path) -> GitObjectSourceProvider:
        manifest = capture_manifest(root, event_name="push",
                                    repository_name="test/repo",
                                    ref="refs/heads/test")
        manifest_path = root.parent / (root.name + "-manifest.json")
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        verified = verify_manifest(root, manifest_path)
        return GitObjectSourceProvider(root, verified)

    def _repository(self, root: Path, pointer: bytes) -> None:
        self._git(root, "init")
        self._git(root, "config", "user.email", "audit-test@example.invalid")
        self._git(root, "config", "user.name", "Audit Test")
        (root / "src").mkdir()
        (root / "src" / "lfs-pointer.dat").write_bytes(pointer)
        (root / "src" / "ordinary.py").write_text("VALUE = 1\n", encoding="utf-8")
        self._git(root, "add", ".")
        self._git(root, "commit", "-m", "LFS pointer fixture")

    def _pointer(self, payload: bytes) -> bytes:
        oid = hashlib.sha256(payload).hexdigest()
        return (f"version https://git-lfs.github.com/spec/v1\n"
                f"oid sha256:{oid}\nsize {len(payload)}\n").encode("ascii")

    def test_pointer_parser_rejects_noncanonical_and_invalid_fields(self):
        valid = self._pointer(b"payload")
        parsed = parse_lfs_pointer(valid)
        self.assertEqual(parsed["size"], 7)
        for invalid in (
            valid.replace(b"size 7\n", b"size 07\n"),
            valid.replace(b"oid sha256:", b"oid sha256:ABC"),
            valid.replace(b"\nsize", b"\nsize 7\nsize"),
            valid[:-1],
            b"version https://git-lfs.github.com/spec/v1\r\n",
        ):
            with self.assertRaises(LfsPayloadVerificationError):
                parse_lfs_pointer(invalid)

    def test_local_payload_is_verified_and_bound_to_source_snapshot(self):
        payload = b"verified LFS payload\x00binary"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            root.mkdir()
            self._repository(root, self._pointer(payload))
            provider = self._provider(root)
            oid = hashlib.sha256(payload).hexdigest()
            store = Path(temp) / "lfs-objects"
            object_path = store / oid[:2] / oid[2:4] / oid
            object_path.parent.mkdir(parents=True)
            object_path.write_bytes(payload)
            report = verify_lfs_payloads(provider, store)
            self.assertEqual(report["pointer_count"], 1)
            self.assertEqual(report["verified_payload_count"], 1)
            self.assertTrue(report["lfs_payload_verified"])
            self.assertEqual(report["source_snapshot_id"], provider.snapshot_identity()["source_snapshot_id"])
            self.assertFalse(report["remote_payload_provenance_verified"])
            self.assertFalse(report["atomic_snapshot_established"])

    def test_missing_or_corrupt_local_payload_abstains(self):
        payload = b"payload"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            root.mkdir()
            self._repository(root, self._pointer(payload))
            provider = self._provider(root)
            store = Path(temp) / "lfs-objects"
            store.mkdir()
            report = verify_lfs_payloads(provider, store)
            self.assertFalse(report["lfs_payload_verified"])
            self.assertIn("lfs_payload_missing", report["records"][0]["reason"])
            oid = hashlib.sha256(payload).hexdigest()
            object_path = store / oid[:2] / oid[2:4] / oid
            object_path.parent.mkdir(parents=True)
            object_path.write_bytes(b"corrupt-content")
            report = verify_lfs_payloads(provider, store)
            self.assertFalse(report["lfs_payload_verified"])
            self.assertIn("lfs_payload_size_mismatch", report["records"][0]["reason"])


    def test_no_cache_emits_complete_unverified_pointer_attestation(self):
        payload = b"payload without local cache"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            root.mkdir()
            self._repository(root, self._pointer(payload))
            provider = self._provider(root)
            report = verify_lfs_payloads(provider)
            self.assertEqual(report["status"], "NOT_SUPPLIED")
            self.assertTrue(report["scan_complete"])
            self.assertEqual(report["scanned_regular_blob_count"], 2)
            self.assertEqual(len(report["regular_blob_inventory"]), 2)
            self.assertEqual(provider._verified_bytes, {},
                             "complete LFS inventory scan must not cache full regular blobs")
            self.assertEqual(report["pointer_count"], 1)
            self.assertEqual(report["unverified_payload_count"], 1)
            self.assertEqual(report["records"][0]["status"], "UNVERIFIED")
            self.assertIn("lfs_object_store_not_supplied", report["records"][0]["reason"])
            self.assertFalse(report["lfs_payload_verified"])
            self.assertFalse(report["production_approval"])
            self.assertEqual(len(report["attestation_sha256"]), 64)

    def test_symlinked_cache_object_is_rejected(self):
        payload = b"payload"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            root.mkdir()
            self._repository(root, self._pointer(payload))
            provider = self._provider(root)
            oid = hashlib.sha256(payload).hexdigest()
            store = Path(temp) / "lfs-objects"
            target = Path(temp) / "payload"
            target.write_bytes(payload)
            object_path = store / oid[:2] / oid[2:4] / oid
            object_path.parent.mkdir(parents=True)
            try:
                object_path.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("host does not permit symlink fixture")
            report = verify_lfs_payloads(provider, store)
            self.assertFalse(report["lfs_payload_verified"])
            self.assertIn("lfs_payload_symlink_rejected", report["records"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
