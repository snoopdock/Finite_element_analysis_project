from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from audit_engine.semantic_audit.ae32c.git_object_source import GitObjectSourceProvider
from audit_engine.semantic_audit.ae32c.submodule_lfs_accounting import account_submodule_lfs
from tools.ae32c_source_snapshot_manifest import capture_manifest, verify_manifest


class SubmoduleLfsAccountingTests(unittest.TestCase):
    def _git(self, root: Path, *args: str, allow_file: bool = False) -> str:
        command = ["git"]
        if allow_file:
            command += ["-c", "protocol.file.allow=always"]
        command += list(args)
        result = subprocess.run(command, cwd=root, text=True, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, check=True)
        return result.stdout.strip()

    def _repo(self, root: Path, files: dict[str, bytes]) -> None:
        root.mkdir(parents=True)
        self._git(root, "init")
        self._git(root, "config", "user.email", "audit-test@example.invalid")
        self._git(root, "config", "user.name", "Audit Test")
        for name, data in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self._git(root, "add", ".")
        self._git(root, "commit", "-m", "fixture")

    def _provider(self, root: Path, temp: Path) -> GitObjectSourceProvider:
        manifest = capture_manifest(root, event_name="push", repository_name="test/repo",
                                    ref="refs/heads/test")
        path = temp / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return GitObjectSourceProvider(root, verify_manifest(root, path))

    def _parent_with_submodule(self, temp: Path, child: Path) -> tuple[Path, str]:
        parent = temp / "parent"
        parent.mkdir()
        self._git(parent, "init")
        self._git(parent, "config", "user.email", "audit-test@example.invalid")
        self._git(parent, "config", "user.name", "Audit Test")
        self._git(parent, "-c", "protocol.file.allow=always", "submodule", "add",
                  str(child), "vendor/child")
        self._git(parent, "add", ".")
        self._git(parent, "commit", "-m", "add submodule")
        return parent, self._git(parent, "rev-parse", "HEAD")

    def _pointer(self, payload: bytes) -> bytes:
        return (f"version https://git-lfs.github.com/spec/v1\n"
                f"oid sha256:{hashlib.sha256(payload).hexdigest()}\n"
                f"size {len(payload)}\n").encode("ascii")

    def test_missing_submodule_repository_is_explicitly_unverified(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            child = temp / "child"
            self._repo(child, {"src/module.py": b"VALUE = 1\n"})
            parent, _ = self._parent_with_submodule(temp, child)
            provider = self._provider(parent, temp)
            report = account_submodule_lfs(provider)
            self.assertEqual(report["gitlink_count"], 1)
            self.assertEqual(report["records"][0]["status"], "NOT_SUPPLIED")
            self.assertFalse(report["recursive_scan_complete"])
            self.assertFalse(report["recursive_content_verified"])
            self.assertFalse(report["network_accessed"])
            self.assertFalse(report["credentials_used"])

    def test_supplied_submodule_is_pinned_and_recursively_scanned(self):
        payload = b"submodule LFS payload"
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            child = temp / "child"
            self._repo(child, {"data/model.bin": self._pointer(payload)})
            parent, _ = self._parent_with_submodule(temp, child)
            provider = self._provider(parent, temp)
            report = account_submodule_lfs(
                provider, submodule_repositories={"vendor/child": child}
            )
            record = report["records"][0]
            self.assertEqual(record["status"], "SCANNED")
            self.assertEqual(record["child_lfs_pointer_count"], 1)
            self.assertEqual(record["child_lfs_unverified_payload_count"], 1)
            self.assertTrue(record["recursive_scan_complete"])
            self.assertFalse(record["recursive_content_verified"])
            self.assertFalse(report["recursive_content_verified"])

    def test_explicit_submodule_lfs_cache_verifies_payload_and_binds_commit(self):
        payload = b"submodule LFS payload"
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            child = temp / "child"
            self._repo(child, {"data/model.bin": self._pointer(payload)})
            parent, _ = self._parent_with_submodule(temp, child)
            provider = self._provider(parent, temp)
            oid = hashlib.sha256(payload).hexdigest()
            store = temp / "lfs-store"
            object_path = store / oid[:2] / oid[2:4] / oid
            object_path.parent.mkdir(parents=True)
            object_path.write_bytes(payload)
            report = account_submodule_lfs(
                provider,
                submodule_repositories={"vendor/child": child},
                lfs_object_stores={"vendor/child": store},
            )
            record = report["records"][0]
            self.assertEqual(record["status"], "SCANNED")
            self.assertEqual(record["child_lfs_status"], "VERIFIED_LOCAL_PAYLOADS")
            self.assertEqual(record["child_lfs_verified_payload_count"], 1)
            self.assertTrue(record["recursive_content_verified"])
            self.assertTrue(report["recursive_content_verified"])


if __name__ == "__main__":
    unittest.main()
