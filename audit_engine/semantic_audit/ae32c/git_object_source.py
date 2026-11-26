"""Immutable committed-tree source provider backed by Git objects."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Iterator


class GitObjectSourceError(RuntimeError):
    """The pinned Git object source cannot be read or verified."""


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class GitObjectSourceProvider:
    """Read committed regular-file bytes from one verified commit/tree identity.

    The checkout is used only to access its Git object database and verify that
    the requested commit/tree exists. Included file bytes are always read by
    object ID; repository paths are never opened from the worktree.
    """

    CONSISTENCY_CLASS = "IMMUTABLE_GIT_OBJECTS"
    SOURCE_SCOPE = "committed_tree_only"

    def __init__(self, repository: str | Path, source_manifest: dict[str, Any]) -> None:
        self.root = Path(repository).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise GitObjectSourceError("repository_not_directory")
        self.manifest = source_manifest
        payload = {key: value for key, value in source_manifest.items() if key != "manifest_sha256"}
        if source_manifest.get("manifest_schema") != "ae32c/source-snapshot-manifest/v1":
            raise GitObjectSourceError("source_manifest_schema_invalid")
        if source_manifest.get("manifest_sha256") != _sha256(_canonical_bytes(payload)):
            raise GitObjectSourceError("source_manifest_digest_mismatch")
        inventory = source_manifest.get("source_inventory")
        if not isinstance(inventory, dict) or not isinstance(inventory.get("entries"), list):
            raise GitObjectSourceError("source_inventory_invalid")
        entries = inventory["entries"]
        if inventory.get("entry_count") != len(entries):
            raise GitObjectSourceError("source_inventory_count_mismatch")
        if inventory.get("sha256") != _sha256(_canonical_bytes(entries)):
            raise GitObjectSourceError("source_inventory_digest_mismatch")
        source = source_manifest.get("source", {})
        self.commit_oid = str(source.get("commit_oid", ""))
        self.root_tree_oid = str(source.get("root_tree_oid", ""))
        self.object_format = str(source.get("commit_oid_algorithm", ""))
        self.snapshot_id = str(source_manifest.get("source_snapshot_id", ""))
        if not self.commit_oid or not self.root_tree_oid or not self.snapshot_id:
            raise GitObjectSourceError("source_identity_missing")
        if hashlib.sha256(_canonical_bytes(source)).hexdigest() != self.snapshot_id:
            raise GitObjectSourceError("source_snapshot_identity_mismatch")
        if source_manifest.get("status") != "VERIFIED" or source_manifest.get("verification", {}).get("status") != "VERIFIED":
            raise GitObjectSourceError("source_manifest_not_verified")

        actual_commit = self._git_text("rev-parse", "--verify", f"{self.commit_oid}^{{commit}}")
        actual_tree = self._git_text("rev-parse", "--verify", f"{self.commit_oid}^{{tree}}")
        actual_format = self._git_text("rev-parse", "--show-object-format")
        if actual_commit != self.commit_oid:
            raise GitObjectSourceError("pinned_commit_oid_mismatch")
        if actual_tree != self.root_tree_oid:
            raise GitObjectSourceError("pinned_root_tree_oid_mismatch")
        if self.object_format and actual_format != self.object_format:
            raise GitObjectSourceError("git_object_format_mismatch")

        raw = self._git_bytes("ls-tree", "-r", "-z", "--full-tree", self.commit_oid)
        tree_entries: list[dict[str, str]] = []
        for record in raw.split(b"\0"):
            if not record:
                continue
            try:
                metadata, path_bytes = record.split(b"\t", 1)
                mode_b, type_b, oid_b = metadata.split(b" ", 2)
                path = path_bytes.decode("utf-8", errors="strict")
                mode = mode_b.decode("ascii")
                object_type = type_b.decode("ascii")
                oid = oid_b.decode("ascii")
            except (ValueError, UnicodeDecodeError) as exc:
                raise GitObjectSourceError("tree_entry_encoding_unsupported") from exc
            tree_entries.append({"path": path, "mode": mode,
                                 "object_type": object_type, "git_object_oid": oid})
        tree_entries.sort(key=lambda item: item["path"].encode("utf-8"))
        if len({item["path"] for item in tree_entries}) != len(tree_entries):
            raise GitObjectSourceError("duplicate_git_tree_path")
        manifest_entries = []
        for item in entries:
            if not isinstance(item, dict):
                raise GitObjectSourceError("source_inventory_entry_invalid")
            manifest_entries.append({key: item.get(key) for key in
                                      ("path", "mode", "object_type", "git_object_oid")})
        manifest_entries.sort(key=lambda item: str(item["path"]).encode("utf-8"))
        if manifest_entries != tree_entries:
            raise GitObjectSourceError("manifest_tree_inventory_mismatch")
        self.entries = {item["path"]: dict(original) for item, original in
                        zip(tree_entries, sorted(entries, key=lambda x: x["path"].encode("utf-8")))}
        self._verified_bytes: dict[str, bytes] = {}

    def _git_bytes(self, *args: str, input_bytes: bytes | None = None) -> bytes:
        completed = subprocess.run(["git", *args], cwd=self.root, input=input_bytes,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if completed.returncode:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            raise GitObjectSourceError("git_command_failed:" + detail[:300])
        return completed.stdout

    def _git_text(self, *args: str, input_bytes: bytes | None = None) -> str:
        try:
            return self._git_bytes(*args, input_bytes=input_bytes).decode("ascii").strip()
        except UnicodeDecodeError as exc:
            raise GitObjectSourceError("git_identity_encoding_invalid") from exc

    def snapshot_identity(self) -> dict[str, Any]:
        return {
            "schema": "ae32c/git-object-source/v1",
            "consistency_class": self.CONSISTENCY_CLASS,
            "source_scope": self.SOURCE_SCOPE,
            "source_snapshot_id": self.snapshot_id,
            "commit_oid": self.commit_oid,
            "root_tree_oid": self.root_tree_oid,
            "object_hash_algorithm": self.object_format,
            "source_inventory_sha256": self.manifest["source_inventory"]["sha256"],
            "entry_count": len(self.entries),
        }

    def iter_entries(self) -> Iterator[dict[str, Any]]:
        for path in sorted(self.entries, key=lambda item: item.encode("utf-8")):
            yield dict(self.entries[path])

    def entry_metadata(self, path: str) -> dict[str, Any]:
        try:
            return dict(self.entries[path])
        except KeyError as exc:
            raise GitObjectSourceError("path_not_in_committed_tree:" + path) from exc

    def read_entry(self, path: str) -> bytes:
        if path in self._verified_bytes:
            return self._verified_bytes[path]
        entry = self.entry_metadata(path)
        if entry.get("object_type") != "blob" or entry.get("mode") not in {"100644", "100755"}:
            raise GitObjectSourceError("entry_not_regular_file_blob:" + path)
        oid = str(entry.get("git_object_oid", ""))
        object_type = self._git_text("cat-file", "-t", oid)
        if object_type != "blob":
            raise GitObjectSourceError("git_object_not_blob:" + oid)
        data = self._git_bytes("cat-file", "blob", oid)
        actual_oid = self._git_text("hash-object", "--stdin", input_bytes=data)
        if actual_oid != oid:
            raise GitObjectSourceError("git_blob_oid_mismatch:" + path)
        expected = entry.get("content_sha256")
        if not isinstance(expected, str) or _sha256(data) != expected:
            raise GitObjectSourceError("git_blob_sha256_mismatch:" + path)
        self._verified_bytes[path] = data
        return data

    def coverage_report(self) -> dict[str, Any]:
        kinds: dict[str, int] = {}
        for entry in self.entries.values():
            kind = str(entry.get("materialization_kind", "unknown"))
            kinds[kind] = kinds.get(kind, 0) + 1
        return {
            "consistency_class": self.CONSISTENCY_CLASS,
            "source_scope": self.SOURCE_SCOPE,
            "entry_count": len(self.entries),
            "verified_blob_count": len(self._verified_bytes),
            "materialization_kinds": dict(sorted(kinds.items())),
            "submodule_content_verified": False,
            "lfs_payload_verified": False,
        }
