from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.ae32c_source_snapshot_manifest import capture_manifest, verify_manifest
from audit_engine.semantic_audit.ae32c.git_object_source import GitObjectSourceProvider
from audit_engine.semantic_audit.ae32a.audit import audit_repository


class GitObjectSourceProviderTests(unittest.TestCase):
    def _git(self, root: Path, *args: str) -> str:
        result = subprocess.run(["git", *args], cwd=root, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return result.stdout.strip()

    def _verified_manifest(self, root: Path) -> dict:
        manifest = self._verified_manifest(root)
        manifest_path = root.parent / (root.name + "-source-manifest.json")
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return verify_manifest(root, manifest_path)

    def _repository(self, root: Path) -> None:
        self._git(root, "init")
        self._git(root, "config", "user.email", "audit-test@example.invalid")
        self._git(root, "config", "user.name", "Audit Test")
        (root / "src").mkdir()
        (root / "src" / "module.py").write_text("VALUE = 'committed'\n", encoding="utf-8")
        (root / ".gitignore").write_text("scratch.py\n", encoding="utf-8")
        self._git(root, "add", ".")
        self._git(root, "commit", "-m", "initial")
        (root / "scratch.py").write_text("UNCOMMITTED = True\n", encoding="utf-8")

    def test_ignored_untracked_source_is_not_in_immutable_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._repository(root)
            manifest = self._verified_manifest(root)
            provider = GitObjectSourceProvider(root, manifest)
            report = audit_repository(root, source_provider=provider)
            paths = {row["path"] for row in report["source_manifest"]}
            self.assertIn("src/module.py", paths)
            self.assertNotIn("scratch.py", paths)
            self.assertEqual(report["audit"]["source_provider"]["consistency_class"],
                             "IMMUTABLE_GIT_OBJECTS")

    def test_worktree_mutation_does_not_change_committed_source_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._repository(root)
            manifest = self._verified_manifest(root)
            provider = GitObjectSourceProvider(root, manifest)
            (root / "src" / "module.py").write_text("VALUE = 'mutated'\n", encoding="utf-8")
            self.assertEqual(provider.read_entry("src/module.py"), b"VALUE = 'committed'\n")
            report = audit_repository(root, source_provider=provider)
            row = next(item for item in report["source_manifest"] if item["path"] == "src/module.py")
            self.assertEqual(row["sha256"], provider.entry_metadata("src/module.py")["content_sha256"])

    def test_manifest_tree_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._repository(root)
            manifest = self._verified_manifest(root)
            manifest["source_inventory"]["entries"][0]["git_object_oid"] = "0" * 40
            from tools.ae32c_source_snapshot_manifest import _seal_manifest
            _seal_manifest(manifest)
            with self.assertRaisesRegex(RuntimeError, "manifest_tree_inventory_mismatch"):
                GitObjectSourceProvider(root, manifest)


if __name__ == "__main__":
    unittest.main()
