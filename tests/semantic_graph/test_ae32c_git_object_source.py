from __future__ import annotations

import hashlib
import json
import os
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
        manifest = capture_manifest(root, event_name="push",
                                    repository_name="test/repo",
                                    ref="refs/heads/test")
        manifest_path = root.parent / (root.name + "-source-manifest.json")
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return verify_manifest(root, manifest_path)

    def _repository(self, root: Path) -> None:
        self._git(root, "init")
        self._git(root, "config", "user.email", "audit-test@example.invalid")
        self._git(root, "config", "user.name", "Audit Test")
        (root / "src").mkdir()
        (root / "src" / "module.py").write_text("VALUE = 'committed'\n", encoding="utf-8")
        (root / "src" / "lfs-pointer.txt").write_text(
            "version https://git-lfs.github.com/spec/v1\n"
            "oid sha256:" + "a" * 64 + "\nsize 123\n", encoding="utf-8")
        self.symlink_available = True
        try:
            (root / "src" / "linked.py").symlink_to("module.py")
        except (OSError, NotImplementedError):
            self.symlink_available = False
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

    def test_symlink_blob_is_not_followed_or_read_as_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._repository(root)
            if not self.symlink_available:
                self.skipTest("host does not permit creating a test symlink")
            provider = GitObjectSourceProvider(root, self._verified_manifest(root))
            from audit_engine.semantic_audit.ae32c.git_object_source import GitObjectSourceError
            with self.assertRaisesRegex(GitObjectSourceError, "entry_not_regular_file_blob"):
                provider.read_entry("src/linked.py")

    def test_lfs_pointer_is_identified_without_claiming_payload_verification(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._repository(root)
            provider = GitObjectSourceProvider(root, self._verified_manifest(root))
            provider.read_entry("src/lfs-pointer.txt")
            coverage = provider.coverage_report()
            self.assertEqual(coverage["lfs_pointer_blob_count"], 1)
            self.assertFalse(coverage["lfs_payload_verified"])

    def test_provider_remains_pinned_after_branch_ref_moves(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._repository(root)
            manifest = self._verified_manifest(root)
            provider = GitObjectSourceProvider(root, manifest)
            pinned_commit = provider.snapshot_identity()["commit_oid"]
            (root / "src" / "module.py").write_text("VALUE = 'new commit'\n", encoding="utf-8")
            self._git(root, "add", "src/module.py")
            self._git(root, "commit", "-m", "move branch after provider construction")
            self.assertNotEqual(self._git(root, "rev-parse", "HEAD"), pinned_commit)
            self.assertEqual(provider.snapshot_identity()["commit_oid"], pinned_commit)
            self.assertEqual(provider.read_entry("src/module.py"), b"VALUE = 'committed'\n")

    def test_worktree_aba_mutation_does_not_change_pinned_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._repository(root)
            provider = GitObjectSourceProvider(root, self._verified_manifest(root))
            source = root / "src" / "module.py"
            original = source.read_bytes()
            source.write_bytes(b"VALUE = 'temporary mutation'\n")
            source.write_bytes(original)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(provider.read_entry("src/module.py"), b"VALUE = 'committed'\n")

    def test_hard_link_replacement_does_not_change_pinned_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._repository(root)
            provider = GitObjectSourceProvider(root, self._verified_manifest(root))
            original = root / "src" / "module.py"
            replacement = root / "replacement.py"
            replacement.write_text("VALUE = 'hard-link target'\n", encoding="utf-8")
            original.unlink()
            try:
                os.link(replacement, original)
            except (OSError, NotImplementedError) as exc:
                self.skipTest("host does not permit hard-link creation: " + str(exc))
            self.assertEqual(original.read_bytes(), replacement.read_bytes())
            self.assertEqual(provider.read_entry("src/module.py"), b"VALUE = 'committed'\n")

    def test_missing_pinned_blob_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._repository(root)
            provider = GitObjectSourceProvider(root, self._verified_manifest(root))
            oid = provider.entry_metadata("src/module.py")["git_object_oid"]
            object_dir = Path(self._git(root, "rev-parse", "--git-path", "objects"))
            if not object_dir.is_absolute():
                object_dir = root / object_dir
            loose_object = object_dir / oid[:2] / oid[2:]
            if not loose_object.is_file():
                self.skipTest("test fixture blob is not stored as a loose object")
            loose_object.chmod(0o666)
            loose_object.unlink()
            from audit_engine.semantic_audit.ae32c.git_object_source import GitObjectSourceError
            with self.assertRaisesRegex(GitObjectSourceError, "git_command_failed"):
                provider.read_entry("src/module.py")

    def test_corrupt_pinned_blob_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._repository(root)
            provider = GitObjectSourceProvider(root, self._verified_manifest(root))
            oid = provider.entry_metadata("src/module.py")["git_object_oid"]
            object_dir = Path(self._git(root, "rev-parse", "--git-path", "objects"))
            if not object_dir.is_absolute():
                object_dir = root / object_dir
            loose_object = object_dir / oid[:2] / oid[2:]
            if not loose_object.is_file():
                self.skipTest("test fixture blob is not stored as a loose object")
            loose_object.chmod(0o644)
            loose_object.write_bytes(b"corrupt-object-data")
            from audit_engine.semantic_audit.ae32c.git_object_source import GitObjectSourceError
            with self.assertRaisesRegex(GitObjectSourceError, "git_command_failed"):
                provider.read_entry("src/module.py")

    def test_gitlink_is_not_read_as_regular_source_blob(self):
        with tempfile.TemporaryDirectory() as temp:
            sandbox = Path(temp)
            root = sandbox / "parent"
            nested = sandbox / "nested"
            root.mkdir()
            nested.mkdir()
            self._repository(root)
            self._git(nested, "init")
            self._git(nested, "config", "user.email", "audit-test@example.invalid")
            self._git(nested, "config", "user.name", "Audit Test")
            (nested / "README.md").write_text("submodule fixture\n", encoding="utf-8")
            self._git(nested, "add", "README.md")
            self._git(nested, "commit", "-m", "nested repository")
            self._git(root, "-c", "protocol.file.allow=always", "submodule", "add",
                      str(nested), "vendor/submodule")
            self._git(root, "commit", "-m", "add submodule fixture")
            provider = GitObjectSourceProvider(root, self._verified_manifest(root))
            metadata = provider.entry_metadata("vendor/submodule")
            self.assertEqual(metadata["mode"], "160000")
            self.assertEqual(metadata["object_type"], "commit")
            from audit_engine.semantic_audit.ae32c.git_object_source import GitObjectSourceError
            with self.assertRaisesRegex(GitObjectSourceError, "entry_not_regular_file_blob"):
                provider.read_entry("vendor/submodule")

    def test_manifest_tree_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._repository(root)
            manifest = self._verified_manifest(root)
            manifest["source_inventory"]["entries"][0]["git_object_oid"] = "0" * 40
            from tools.ae32c_source_snapshot_manifest import _canonical_bytes, _seal_manifest
            inventory = manifest["source_inventory"]
            inventory["sha256"] = hashlib.sha256(_canonical_bytes(inventory["entries"])).hexdigest()
            manifest["source"]["source_inventory_sha256"] = inventory["sha256"]
            manifest["source_snapshot_id"] = hashlib.sha256(_canonical_bytes(manifest["source"])).hexdigest()
            _seal_manifest(manifest)
            with self.assertRaisesRegex(RuntimeError, "manifest_tree_inventory_mismatch"):
                GitObjectSourceProvider(root, manifest)


    def test_replacement_ref_cannot_change_pinned_commit_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._repository(root)
            manifest = self._verified_manifest(root)
            pinned = self._git(root, "rev-parse", "HEAD")
            (root / "src" / "module.py").write_text("VALUE = 'replacement commit'\n", encoding="utf-8")
            self._git(root, "add", "src/module.py")
            self._git(root, "commit", "-m", "replacement target")
            replacement = self._git(root, "rev-parse", "HEAD")
            self._git(root, "replace", pinned, replacement)
            provider = GitObjectSourceProvider(root, manifest)
            self.assertEqual(provider.snapshot_identity()["commit_oid"], pinned)
            self.assertEqual(provider.read_entry("src/module.py"), b"VALUE = 'committed'\n")

    def test_inherited_git_repository_routing_environment_is_ignored(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            sandbox = Path(temp)
            root = sandbox / "target"
            other = sandbox / "other"
            root.mkdir()
            other.mkdir()
            self._repository(root)
            self._git(other, "init")
            self._git(other, "config", "user.email", "other@example.invalid")
            self._git(other, "config", "user.name", "Other")
            (other / "foreign.txt").write_text("foreign\n", encoding="utf-8")
            self._git(other, "add", ".")
            self._git(other, "commit", "-m", "foreign repository")
            with patch.dict(os.environ, {
                "GIT_DIR": str(other / ".git"),
                "GIT_WORK_TREE": str(other),
                "GIT_OBJECT_DIRECTORY": str(other / ".git" / "objects"),
                "GIT_NO_REPLACE_OBJECTS": "0",
                "GIT_NO_LAZY_FETCH": "0",
            }):
                manifest = self._verified_manifest(root)
                provider = GitObjectSourceProvider(root, manifest)
            self.assertEqual(provider.snapshot_identity()["commit_oid"],
                             self._git(root, "rev-parse", "HEAD"))
            paths = {item["path"] for item in provider.iter_entries()}
            self.assertIn("src/module.py", paths)
            self.assertNotIn("foreign.txt", paths)

    def test_sha256_object_format_repository_is_supported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = subprocess.run(["git", "init", "--object-format=sha256"], cwd=root,
                                    text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode:
                self.skipTest("installed Git does not support SHA-256 repositories")
            self._git(root, "config", "user.email", "audit-test@example.invalid")
            self._git(root, "config", "user.name", "Audit Test")
            (root / "src").mkdir()
            (root / "src" / "module.py").write_text("VALUE = 'sha256'\n", encoding="utf-8")
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "sha256 object format")
            provider = GitObjectSourceProvider(root, self._verified_manifest(root))
            self.assertEqual(provider.snapshot_identity()["object_hash_algorithm"], "sha256")
            self.assertEqual(provider.read_entry("src/module.py"), b"VALUE = 'sha256'\n")


    def test_external_object_alternates_are_rejected_by_capture_and_provider(self):
        from tools.ae32c_source_snapshot_manifest import SnapshotError
        with tempfile.TemporaryDirectory() as temp:
            sandbox = Path(temp)
            root = sandbox / "repo"
            alternate = sandbox / "alternate.git"
            root.mkdir()
            self._repository(root)
            manifest = self._verified_manifest(root)
            self._git(sandbox, "clone", "--bare", str(root), str(alternate))
            object_dir = Path(self._git(root, "rev-parse", "--git-path", "objects"))
            if not object_dir.is_absolute():
                object_dir = root / object_dir
            alternates = object_dir / "info" / "alternates"
            alternates.parent.mkdir(parents=True, exist_ok=True)
            alternates.write_text(str(alternate / "objects") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(SnapshotError, "external_object_store_not_allowed"):
                capture_manifest(root, event_name="push", repository_name="test/repo",
                                 ref="refs/heads/test")
            from audit_engine.semantic_audit.ae32c.git_object_source import GitObjectSourceError
            with self.assertRaisesRegex(GitObjectSourceError, "external_object_store_not_allowed"):
                GitObjectSourceProvider(root, manifest)

    def test_shallow_repository_tree_is_read_without_history_assumptions(self):
        with tempfile.TemporaryDirectory() as temp:
            sandbox = Path(temp)
            source = sandbox / "source"
            shallow = sandbox / "shallow"
            source.mkdir()
            self._repository(source)
            self._git(sandbox, "clone", "--depth=1", "file://" + str(source), str(shallow))
            shallow_file = Path(self._git(shallow, "rev-parse", "--git-path", "shallow"))
            self.assertTrue(shallow_file.is_file())
            provider = GitObjectSourceProvider(shallow, self._verified_manifest(shallow))
            self.assertEqual(provider.read_entry("src/module.py"), b"VALUE = 'committed'\n")

    def test_grafts_do_not_change_pinned_commit_tree_content(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._repository(root)
            manifest = self._verified_manifest(root)
            pinned = self._git(root, "rev-parse", "HEAD")
            (root / "src" / "module.py").write_text("VALUE = 'later commit'\n", encoding="utf-8")
            self._git(root, "add", "src/module.py")
            self._git(root, "commit", "-m", "graft parent candidate")
            graft_parent = self._git(root, "rev-parse", "HEAD")
            grafts = Path(self._git(root, "rev-parse", "--git-path", "info/grafts"))
            if not grafts.is_absolute():
                grafts = root / grafts
            grafts.parent.mkdir(parents=True, exist_ok=True)
            grafts.write_text(pinned + " " + graft_parent + "\n", encoding="ascii")
            provider = GitObjectSourceProvider(root, manifest)
            self.assertEqual(provider.snapshot_identity()["commit_oid"], pinned)
            self.assertEqual(provider.read_entry("src/module.py"), b"VALUE = 'committed'\n")

    def test_missing_promisor_blob_does_not_trigger_lazy_fetch(self):
        with tempfile.TemporaryDirectory() as temp:
            sandbox = Path(temp)
            root = sandbox / "repo"
            remote = sandbox / "remote.git"
            root.mkdir()
            self._repository(root)
            manifest = self._verified_manifest(root)
            self._git(sandbox, "clone", "--bare", str(root), str(remote))
            self._git(root, "config", "extensions.partialClone", "origin")
            self._git(root, "config", "remote.origin.promisor", "true")
            self._git(root, "config", "remote.origin.url", "file://" + str(remote))
            provider = GitObjectSourceProvider(root, manifest)
            oid = provider.entry_metadata("src/module.py")["git_object_oid"]
            object_dir = Path(self._git(root, "rev-parse", "--git-path", "objects"))
            if not object_dir.is_absolute():
                object_dir = root / object_dir
            loose_object = object_dir / oid[:2] / oid[2:]
            if not loose_object.is_file():
                self.skipTest("test fixture blob is not stored as a loose object")
            loose_object.chmod(0o666)
            loose_object.unlink()
            from audit_engine.semantic_audit.ae32c.git_object_source import GitObjectSourceError
            with self.assertRaisesRegex(GitObjectSourceError, "git_command_failed"):
                provider.read_entry("src/module.py")
            self.assertFalse(loose_object.exists(), "provider unexpectedly restored the promisor object")

    def test_gitlink_is_reported_as_pointer_and_never_as_verified_submodule_content(self):
        with tempfile.TemporaryDirectory() as temp:
            sandbox = Path(temp)
            root = sandbox / "superproject"
            dependency = sandbox / "dependency"
            root.mkdir()
            dependency.mkdir()
            self._repository(root)
            self._git(dependency, "init")
            self._git(dependency, "config", "user.email", "audit-test@example.invalid")
            self._git(dependency, "config", "user.name", "Audit Test")
            (dependency / "dependency.py").write_text("DEPENDENCY = True\\n", encoding="utf-8")
            self._git(dependency, "add", ".")
            self._git(dependency, "commit", "-m", "submodule initial commit")
            pinned_commit = self._git(dependency, "rev-parse", "HEAD")

            # Use a real initialized submodule so the superproject worktree is
            # clean at capture time; a bare index gitlink is a dirty fixture.
            self._git(root, "-c", "protocol.file.allow=always", "submodule",
                      "add", str(dependency), "vendor/dependency")
            self._git(root, "commit", "-m", "record submodule gitlink")
            manifest = self._verified_manifest(root)
            provider = GitObjectSourceProvider(root, manifest)

            coverage = provider.coverage_report()
            self.assertEqual(coverage["submodule_entry_count"], 1)
            self.assertEqual(coverage["submodule_resolution_policy"],
                             "POINTER_ONLY_NO_NETWORK_NO_CHECKOUT")
            self.assertFalse(coverage["submodule_content_verified"])
            self.assertEqual(coverage["submodule_entries"], [{
                "path": "vendor/dependency",
                "expected_commit_oid": pinned_commit,
                "pointer_status": "SUPERPROJECT_GITLINK_VERIFIED",
                "content_status": "UNVERIFIED_EXTERNAL_REPOSITORY",
                "recursive_content_verified": False,
            }])

            from audit_engine.semantic_audit.ae32c.git_object_source import GitObjectSourceError
            with self.assertRaisesRegex(GitObjectSourceError, "entry_not_regular_file_blob"):
                provider.read_entry("vendor/dependency")

    def test_repository_without_gitlinks_reports_empty_submodule_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._repository(root)
            provider = GitObjectSourceProvider(root, self._verified_manifest(root))
            coverage = provider.coverage_report()
            self.assertEqual(coverage["submodule_entry_count"], 0)
            self.assertEqual(coverage["submodule_entries"], [])
            self.assertFalse(coverage["submodule_content_verified"])

    def test_object_disappearance_between_type_check_and_read_fails_closed(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._repository(root)
            provider = GitObjectSourceProvider(root, self._verified_manifest(root))
            oid = provider.entry_metadata("src/module.py")["git_object_oid"]
            object_dir = Path(self._git(root, "rev-parse", "--git-path", "objects"))
            if not object_dir.is_absolute():
                object_dir = root / object_dir
            loose_object = object_dir / oid[:2] / oid[2:]
            if not loose_object.is_file():
                self.skipTest("test fixture blob is not stored as a loose object")
            original_git_bytes = provider._git_bytes
            removed = False
            def remove_after_type_check(*args, input_bytes=None):
                nonlocal removed
                result = original_git_bytes(*args, input_bytes=input_bytes)
                if args[:2] == ("cat-file", "-t") and not removed:
                    loose_object.chmod(0o666)
                    loose_object.unlink()
                    removed = True
                return result
            from audit_engine.semantic_audit.ae32c.git_object_source import GitObjectSourceError
            with patch.object(provider, "_git_bytes", side_effect=remove_after_type_check):
                with self.assertRaisesRegex(GitObjectSourceError, "git_command_failed"):
                    provider.read_entry("src/module.py")
            self.assertTrue(removed)
            self.assertNotIn("src/module.py", provider._verified_bytes)


if __name__ == "__main__":
    unittest.main()
