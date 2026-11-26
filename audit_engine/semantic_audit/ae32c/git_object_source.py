"""Immutable committed-tree source provider backed by Git objects."""
from __future__ import annotations

import hashlib
import json
import os
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
    _STREAM_CHUNK_SIZE = 1024 * 1024

    def __init__(self, repository: str | Path, source_manifest: dict[str, Any]) -> None:
        self.root = Path(repository).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise GitObjectSourceError("repository_not_directory")
        self._assert_no_external_object_stores()
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
        # A mode-160000 gitlink is a commit pointer owned by another repository.
        # The superproject tree does not contain that repository's file inventory.
        # Keep the pointer explicit; never interpret it as an ordinary blob or
        # infer recursive verification from the presence of a checked-out path.
        self._submodule_entries = [
            {
                "path": path,
                "expected_commit_oid": str(entry.get("git_object_oid", "")),
                "pointer_status": "SUPERPROJECT_GITLINK_VERIFIED",
                "content_status": "UNVERIFIED_EXTERNAL_REPOSITORY",
                "recursive_content_verified": False,
            }
            for path, entry in sorted(self.entries.items(),
                                      key=lambda item: item[0].encode("utf-8"))
            if entry.get("mode") == "160000" and entry.get("object_type") == "commit"
        ]
        self._verified_bytes: dict[str, bytes] = {}
        self._lfs_pointer_paths: set[str] = set()

    @staticmethod
    def _git_environment() -> dict[str, str]:
        # Git repository-routing and object-lookup variables are ambient authority.
        # The provider is bound to self.root and must not inherit a caller's
        # alternate repository, object directory, namespace, replacement policy,
        # or lazy-fetch behavior.
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("GIT_")}
        env.update({
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
        })
        return env

    def _assert_no_external_object_stores(self) -> None:
        # Object alternates are outside this repository's declared source trust
        # boundary. Content hashes still detect corruption, but cannot establish
        # the provenance or availability of an external object store.
        for relative in ("objects/info/alternates", "objects/info/http-alternates"):
            raw_path = Path(self._git_text("rev-parse", "--git-path", relative))
            path = raw_path if raw_path.is_absolute() else self.root / raw_path
            try:
                configured = path.is_file() and bool(path.read_text(encoding="utf-8").strip())
            except (OSError, UnicodeError) as exc:
                raise GitObjectSourceError("object_alternates_metadata_unreadable") from exc
            if configured:
                raise GitObjectSourceError("external_object_store_not_allowed:" + relative)

    def _git_bytes(self, *args: str, input_bytes: bytes | None = None) -> bytes:
        completed = subprocess.run(["git", *args], cwd=self.root, env=self._git_environment(),
                                   input=input_bytes, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, check=False)
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
        if data.startswith(b"version https://git-lfs.github.com/spec/v1\n"):
            self._lfs_pointer_paths.add(path)
        self._verified_bytes[path] = data
        return data

    def read_entry_prefix(self, path: str, max_bytes: int = 1024) -> tuple[bytes, int]:
        """Verify a committed blob while retaining only a bounded content prefix.

        This path is intended for classification scans over the complete tree.
        It streams the full Git object through both the Git object hash and the
        manifest SHA-256 check without populating the provider's full-byte cache.
        """
        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
            raise GitObjectSourceError("blob_prefix_limit_invalid")
        entry = self.entry_metadata(path)
        if entry.get("object_type") != "blob" or entry.get("mode") not in {"100644", "100755"}:
            raise GitObjectSourceError("entry_not_regular_file_blob:" + path)
        oid = str(entry.get("git_object_oid", ""))
        try:
            git_digest = hashlib.new(self.object_format)
        except ValueError as exc:
            raise GitObjectSourceError("git_object_hash_algorithm_unsupported") from exc
        content_digest = hashlib.sha256()
        prefix = bytearray()
        process = subprocess.Popen(
            ["git", "cat-file", "--batch"], cwd=self.root, env=self._git_environment(),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        try:
            assert process.stdin is not None and process.stdout is not None
            process.stdin.write(oid.encode("ascii") + b"\n")
            process.stdin.flush()
            header = process.stdout.readline().rstrip(b"\n").split()
            if (len(header) != 3 or header[0].decode("ascii", errors="replace") != oid
                    or header[1] != b"blob"):
                raise GitObjectSourceError("git_blob_header_invalid:" + path)
            try:
                size = int(header[2])
            except ValueError as exc:
                raise GitObjectSourceError("git_blob_size_invalid:" + path) from exc
            git_digest.update(f"blob {size}\0".encode("ascii"))
            remaining = size
            while remaining:
                chunk = process.stdout.read(min(self._STREAM_CHUNK_SIZE, remaining))
                if not chunk:
                    raise GitObjectSourceError("git_blob_truncated:" + path)
                git_digest.update(chunk)
                content_digest.update(chunk)
                if len(prefix) < max_bytes:
                    prefix.extend(chunk[:max_bytes - len(prefix)])
                remaining -= len(chunk)
            if process.stdout.read(1) != b"\n":
                raise GitObjectSourceError("git_blob_terminator_invalid:" + path)
            process.stdin.close()
            stderr = process.stderr.read() if process.stderr else b""
            if process.wait() != 0:
                raise GitObjectSourceError(
                    "git_command_failed:" + stderr.decode("utf-8", errors="replace")[:300]
                )
        except (OSError, UnicodeError) as exc:
            raise GitObjectSourceError("git_blob_stream_failed:" + path) from exc
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None and not stream.closed:
                    stream.close()
        if git_digest.hexdigest() != oid:
            raise GitObjectSourceError("git_blob_oid_mismatch:" + path)
        expected = entry.get("content_sha256")
        if not isinstance(expected, str) or content_digest.hexdigest() != expected:
            raise GitObjectSourceError("git_blob_sha256_mismatch:" + path)
        return bytes(prefix), size

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
            "lfs_pointer_blob_count": len(self._lfs_pointer_paths),
            "lfs_pointer_paths": sorted(self._lfs_pointer_paths),
            "submodule_entry_count": len(self._submodule_entries),
            "submodule_entries": [dict(item) for item in self._submodule_entries],
            "submodule_content_verified": False,
            "submodule_resolution_policy": "POINTER_ONLY_NO_NETWORK_NO_CHECKOUT",
            "lfs_payload_verified": False,
        }
