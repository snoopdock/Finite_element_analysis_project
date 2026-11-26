#!/usr/bin/env python3
"""Capture and verify a Git-backed source snapshot manifest."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

SCHEMA = "ae32c/source-snapshot-manifest/v1"
CHUNK_SIZE = 1024 * 1024


class SnapshotError(RuntimeError):
    """A source snapshot could not be established or verified."""


def _git_environment() -> dict[str, str]:
    # Pin Git discovery/object semantics to the requested checkout. In
    # particular, ignore inherited repository-routing variables, replacement
    # refs and partial-clone lazy fetching.
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _seal_manifest(manifest: dict[str, Any]) -> None:
    payload = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    manifest["manifest_sha256"] = _sha256(payload)


def _git(root: Path, *args: str) -> bytes:
    completed = subprocess.run(["git", *args], cwd=root, env=_git_environment(),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise SnapshotError(f"git_command_failed:{args[0]}:{detail[:500]}")
    return completed.stdout


def _git_text(root: Path, *args: str) -> str:
    return _git(root, *args).decode("utf-8", errors="strict").strip()


def _working_tree_state(root: Path) -> dict[str, Any]:
    raw = _git(root, "status", "--porcelain=v1", "-z",
               "--untracked-files=all", "--ignore-submodules=none")
    records = [item for item in raw.split(b"\0") if item]
    sample = [item.decode("utf-8", errors="replace")[:500] for item in records[:25]]
    return {"clean": not records, "changed_entry_count": len(records),
            "changed_entries_sample": sample}


def _tree_entries(root: Path) -> list[dict[str, Any]]:
    raw = _git(root, "ls-tree", "-r", "-z", "--full-tree", "HEAD")
    entries: list[dict[str, Any]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            metadata, path_bytes = record.split(b"\t", 1)
            mode_b, type_b, oid_b = metadata.split(b" ", 2)
            path = path_bytes.decode("utf-8", errors="strict")
            mode, object_type, oid = (mode_b.decode("ascii"), type_b.decode("ascii"),
                                      oid_b.decode("ascii"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise SnapshotError("tree_entry_encoding_unsupported") from exc
        entries.append({"path": path, "mode": mode, "object_type": object_type,
                        "git_object_oid": oid})
    entries.sort(key=lambda item: item["path"].encode("utf-8"))
    return entries


def _blob_content_digests(root: Path, entries: list[dict[str, Any]]) -> dict[str, str]:
    """Hash unique Git blob contents with bounded per-object memory."""
    object_ids = sorted({item["git_object_oid"] for item in entries
                         if item["object_type"] == "blob"})
    if not object_ids:
        return {}
    process = subprocess.Popen(["git", "cat-file", "--batch"], cwd=root, env=_git_environment(),
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    assert process.stdin is not None and process.stdout is not None
    digests: dict[str, str] = {}
    try:
        for oid in object_ids:
            process.stdin.write(oid.encode("ascii") + b"\n")
            process.stdin.flush()
            parts = process.stdout.readline().rstrip(b"\n").split()
            if len(parts) != 3 or parts[0].decode("ascii", errors="replace") != oid:
                raise SnapshotError(f"git_blob_header_invalid:{oid}")
            if parts[1] != b"blob":
                raise SnapshotError(f"git_object_not_blob:{oid}")
            try:
                remaining = int(parts[2])
            except ValueError as exc:
                raise SnapshotError(f"git_blob_size_invalid:{oid}") from exc
            digest = hashlib.sha256()
            while remaining:
                chunk = process.stdout.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    raise SnapshotError(f"git_blob_truncated:{oid}")
                digest.update(chunk)
                remaining -= len(chunk)
            if process.stdout.read(1) != b"\n":
                raise SnapshotError(f"git_blob_terminator_invalid:{oid}")
            digests[oid] = digest.hexdigest()
        process.stdin.close()
        stderr = process.stderr.read() if process.stderr else b""
        if process.wait() != 0:
            raise SnapshotError("git_cat_file_failed:" +
                                stderr.decode("utf-8", errors="replace")[:500])
    finally:
        if process.poll() is None:
            try:
                if process.stdin and not process.stdin.closed:
                    process.stdin.close()
            except OSError:
                pass
            process.kill()
            process.wait()
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()
    return digests


def _reject_external_object_stores(root: Path) -> None:
    for relative in ("objects/info/alternates", "objects/info/http-alternates"):
        raw_path = Path(_git_text(root, "rev-parse", "--git-path", relative))
        path = raw_path if raw_path.is_absolute() else root / raw_path
        try:
            configured = path.is_file() and bool(path.read_text(encoding="utf-8").strip())
        except (OSError, UnicodeError) as exc:
            raise SnapshotError("object_alternates_metadata_unreadable") from exc
        if configured:
            raise SnapshotError("external_object_store_not_allowed:" + relative)


def _event_context(event_name, repository_name, ref, event_path) -> dict[str, Any]:
    name = event_name or os.environ.get("GITHUB_EVENT_NAME", "unknown")
    repository = repository_name or os.environ.get("GITHUB_REPOSITORY", "unknown/unknown")
    context = {
        "event_name": name, "repository": repository,
        "ref": ref or os.environ.get("GITHUB_REF", ""),
        "source_mode": {"push": "push", "pull_request": "pull_request_merge",
                        "workflow_dispatch": "manual", "schedule": "scheduled"}.get(
                            name, "github_event"),
        "base_commit_oid": None, "head_commit_oid": None,
        "event_merge_commit_oid": None,
    }
    path = Path(event_path) if event_path else (
        Path(os.environ["GITHUB_EVENT_PATH"]) if os.environ.get("GITHUB_EVENT_PATH") else None)
    if name == "pull_request":
        if path is None or not path.is_file():
            raise SnapshotError("pull_request_event_payload_missing")
        try:
            pr = json.loads(path.read_text(encoding="utf-8"))["pull_request"]
            context["base_commit_oid"] = pr["base"]["sha"]
            context["head_commit_oid"] = pr["head"]["sha"]
            context["event_merge_commit_oid"] = pr.get("merge_commit_sha")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise SnapshotError("pull_request_event_payload_invalid") from exc
        if not context["base_commit_oid"] or not context["head_commit_oid"]:
            raise SnapshotError("pull_request_base_or_head_identity_missing")
    return context


def _build_snapshot(repository, *, expected_source_revision=None, event_name=None,
                    repository_name=None, ref=None, event_path=None,
                    recorded_event=None) -> dict[str, Any]:
    root = Path(repository).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise SnapshotError("repository_not_directory")
    _reject_external_object_stores(root)
    commit_oid = _git_text(root, "rev-parse", "HEAD")
    if expected_source_revision and commit_oid.lower() != expected_source_revision.lower():
        raise SnapshotError("checked_out_commit_does_not_match_expected_source_revision")
    root_tree_oid = _git_text(root, "rev-parse", "HEAD^{tree}")
    object_format = _git_text(root, "rev-parse", "--show-object-format")
    entries = _tree_entries(root)
    blob_digests = _blob_content_digests(root, entries)
    for item in entries:
        if item["object_type"] == "blob":
            item["content_sha256"] = blob_digests[item["git_object_oid"]]
            item["materialization_kind"] = "symlink" if item["mode"] == "120000" else "regular_file"
        elif item["object_type"] == "commit" and item["mode"] == "160000":
            item["content_sha256"] = None
            item["materialization_kind"] = "gitlink_submodule"
        else:
            raise SnapshotError(f"unsupported_git_tree_entry:{item['mode']}:{item['object_type']}")
    inventory_sha256 = _sha256(entries)
    if recorded_event is None:
        event = _event_context(event_name, repository_name, ref, event_path)
    else:
        required_event_fields = (
            "event_name", "repository", "ref", "source_mode",
            "base_commit_oid", "head_commit_oid", "event_merge_commit_oid",
        )
        if not isinstance(recorded_event, dict) or any(
            field not in recorded_event for field in required_event_fields
        ):
            raise SnapshotError("recorded_event_context_invalid")
        event = {field: recorded_event[field] for field in required_event_fields}
    source = {
        "repository": event["repository"], "source_mode": event["source_mode"],
        "commit_oid": commit_oid, "commit_oid_algorithm": object_format,
        "root_tree_oid": root_tree_oid, "base_commit_oid": event["base_commit_oid"],
        "head_commit_oid": event["head_commit_oid"],
        "source_inventory_sha256": inventory_sha256,
    }
    worktree = _working_tree_state(root)
    return {
        "source_snapshot_id": _sha256(source), "source": source, "event": event,
        "source_inventory": {"schema": "ae32c/source-inventory/v1",
                             "entry_count": len(entries), "entries": entries,
                             "sha256": inventory_sha256},
        "materialization": {
            "checkout_commit_oid": commit_oid, "checkout_root_tree_oid": root_tree_oid,
            "worktree": worktree, "status": "CLEAN" if worktree["clean"] else "DIRTY",
            "submodule_and_lfs_limitations": (
                "Gitlink entries identify submodule commit pointers; submodule worktrees "
                "are not recursively verified. Git LFS pointer blobs are hashed as Git "
                "objects; external LFS payload bytes are not verified by this tool."
            ),
        },
    }


def capture_manifest(repository, *, expected_source_revision=None, event_name=None,
                     repository_name=None, ref=None, event_path=None) -> dict[str, Any]:
    snapshot = _build_snapshot(repository, expected_source_revision=expected_source_revision,
                               event_name=event_name, repository_name=repository_name,
                               ref=ref, event_path=event_path)
    if not snapshot["materialization"]["worktree"]["clean"]:
        raise SnapshotError("worktree_not_clean_at_capture")
    now = _utc_now()
    manifest = {
        "manifest_schema": SCHEMA, "status": "CAPTURED_PENDING_POSTFLIGHT",
        "created_at": now, "source_snapshot_id": snapshot["source_snapshot_id"],
        "source": snapshot["source"], "event": snapshot["event"],
        "source_inventory": snapshot["source_inventory"],
        "materialization": snapshot["materialization"],
        "verification": {
            "status": "PENDING", "captured_at": now, "verified_at": None,
            "source_snapshot_id_at_verification": None,
            "source_inventory_sha256_at_verification": None,
            "worktree_clean_at_verification": None, "reason": None,
        },
        "run": {"workflow": os.environ.get("GITHUB_WORKFLOW"),
                "run_id": os.environ.get("GITHUB_RUN_ID"),
                "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
                "actor": os.environ.get("GITHUB_ACTOR")},
        "authority": {"atomic_repository_snapshot_established": False,
                      "graph_completeness_established": False,
                      "production_approval": False},
    }
    _seal_manifest(manifest)
    return manifest


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    _seal_manifest(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(_canonical_bytes(value))
    temporary.replace(path)


def verify_manifest(repository, manifest_path, *, expected_source_revision=None) -> dict[str, Any]:
    path = Path(manifest_path)
    manifest = None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or manifest.get("manifest_schema") != SCHEMA:
            raise SnapshotError("manifest_schema_invalid")
        submitted_manifest_digest = manifest.get("manifest_sha256")
        payload = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
        if submitted_manifest_digest != _sha256(payload):
            raise SnapshotError("manifest_digest_mismatch")
        inventory = manifest.get("source_inventory")
        if not isinstance(inventory, dict) or not isinstance(inventory.get("entries"), list):
            raise SnapshotError("manifest_inventory_invalid")
        if (inventory.get("entry_count") != len(inventory["entries"])
                or inventory.get("sha256") != _sha256(inventory["entries"])):
            raise SnapshotError("manifest_inventory_digest_mismatch")
        snapshot = _build_snapshot(
            repository,
            expected_source_revision=expected_source_revision,
            recorded_event=manifest.get("event"),
        )
        same = (
            snapshot["source_snapshot_id"] == manifest.get("source_snapshot_id")
            and snapshot["source"] == manifest.get("source")
            and snapshot["source_inventory"]["sha256"]
            == manifest.get("source_inventory", {}).get("sha256")
            and snapshot["source_inventory"]["entries"]
            == manifest.get("source_inventory", {}).get("entries")
            and snapshot["source"]["root_tree_oid"]
            == manifest.get("source", {}).get("root_tree_oid")
        )
        if not same:
            raise SnapshotError("source_identity_changed_after_capture")
        if not snapshot["materialization"]["worktree"]["clean"]:
            raise SnapshotError("worktree_not_clean_at_postflight")
        manifest["verification"] = {
            "status": "VERIFIED",
            "captured_at": manifest.get("verification", {}).get("captured_at"),
            "verified_at": _utc_now(),
            "source_snapshot_id_at_verification": snapshot["source_snapshot_id"],
            "source_inventory_sha256_at_verification": snapshot["source_inventory"]["sha256"],
            "worktree_clean_at_verification": True, "reason": None,
        }
        manifest["status"] = "VERIFIED"
        _atomic_write(path, manifest)
        return manifest
    except Exception as exc:
        if isinstance(manifest, dict):
            manifest["status"] = "FAILED"
            manifest["verification"] = {
                "status": "FAILED",
                "captured_at": manifest.get("verification", {}).get("captured_at"),
                "verified_at": _utc_now(),
                "source_snapshot_id_at_verification": None,
                "source_inventory_sha256_at_verification": None,
                "worktree_clean_at_verification": False, "reason": str(exc)[:500],
            }
            _atomic_write(path, manifest)
        if isinstance(exc, SnapshotError):
            raise
        raise SnapshotError(f"manifest_verification_failed:{exc}") from exc


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("capture")
    capture.add_argument("--repository", default=".")
    capture.add_argument("--output", required=True)
    capture.add_argument("--expected-source-revision", default=os.environ.get("GITHUB_SHA"))
    capture.add_argument("--event-name", default=os.environ.get("GITHUB_EVENT_NAME"))
    capture.add_argument("--repository-name", default=os.environ.get("GITHUB_REPOSITORY"))
    capture.add_argument("--ref", default=os.environ.get("GITHUB_REF"))
    capture.add_argument("--event-path", default=os.environ.get("GITHUB_EVENT_PATH"))
    verify = commands.add_parser("verify")
    verify.add_argument("--repository", default=".")
    verify.add_argument("--manifest", required=True)
    verify.add_argument("--expected-source-revision", default=os.environ.get("GITHUB_SHA"))
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "capture":
            manifest = capture_manifest(
                args.repository, expected_source_revision=args.expected_source_revision,
                event_name=args.event_name, repository_name=args.repository_name,
                ref=args.ref, event_path=args.event_path)
            _atomic_write(Path(args.output), manifest)
            print(json.dumps({"status": manifest["status"],
                              "source_snapshot_id": manifest["source_snapshot_id"],
                              "commit_oid": manifest["source"]["commit_oid"],
                              "root_tree_oid": manifest["source"]["root_tree_oid"],
                              "source_inventory_sha256": manifest["source_inventory"]["sha256"],
                              "entry_count": manifest["source_inventory"]["entry_count"]},
                             sort_keys=True))
        else:
            manifest = verify_manifest(args.repository, args.manifest,
                                       expected_source_revision=args.expected_source_revision)
            print(json.dumps({"status": manifest["status"],
                              "source_snapshot_id": manifest["source_snapshot_id"],
                              "verified_at": manifest["verification"]["verified_at"]},
                             sort_keys=True))
        return 0
    except (SnapshotError, OSError, ValueError) as exc:
        print(f"source_snapshot_error:{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
