"""Bounded, offline recursive accounting for committed Git submodule gitlinks."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Mapping


class SubmoduleAccountingError(RuntimeError):
    """A supplied submodule repository cannot be safely inspected."""


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _git_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update({"GIT_NO_REPLACE_OBJECTS": "1", "GIT_NO_LAZY_FETCH": "1",
                "GIT_OPTIONAL_LOCKS": "0", "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull})
    return env


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, env=_git_env(),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise SubmoduleAccountingError("submodule_git_unavailable")
    try:
        return result.stdout.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise SubmoduleAccountingError("submodule_git_identity_invalid") from exc


def _verified_provider(root: Path, expected_commit: str):
    from audit_engine.semantic_audit.ae32c.git_object_source import GitObjectSourceProvider
    from tools.ae32c_source_snapshot_manifest import capture_manifest, verify_manifest

    actual = _git(root, "rev-parse", "--verify", "HEAD^{commit}")
    if actual != expected_commit:
        raise SubmoduleAccountingError("submodule_commit_mismatch")
    with tempfile.TemporaryDirectory(prefix="ae32c-submodule-") as temp:
        manifest_path = Path(temp) / "source-manifest.json"
        manifest = capture_manifest(
            root, event_name="submodule_local_inspection",
            repository_name="local/submodule", ref=expected_commit,
        )
        manifest_path.write_bytes(_canonical_bytes(manifest))
        verified = verify_manifest(root, manifest_path, expected_source_revision=expected_commit)
        # Provider validates the complete manifest and reads only committed Git objects.
        return GitObjectSourceProvider(root, verified)


def account_submodule_lfs(
    provider: Any,
    *,
    submodule_repositories: Mapping[str, str | Path] | None = None,
    lfs_object_stores: Mapping[str, str | Path] | None = None,
    max_depth: int = 8,
    max_repositories: int = 256,
) -> dict[str, Any]:
    """Account for every gitlink; recurse only into explicitly supplied local repositories.

    Mapping keys are paths relative to the superproject (nested paths use
    `parent/submodule/child`). No clone, fetch, checkout, credential, or network
    operation is performed. Missing or mismatched repositories remain unverified.
    """
    if not isinstance(max_depth, int) or isinstance(max_depth, bool) or max_depth < 0:
        raise SubmoduleAccountingError("submodule_max_depth_invalid")
    if not isinstance(max_repositories, int) or isinstance(max_repositories, bool) or max_repositories < 1:
        raise SubmoduleAccountingError("submodule_repository_budget_invalid")
    repositories = dict(submodule_repositories or {})
    stores = dict(lfs_object_stores or {})
    visited = 0

    def walk(current_provider: Any, prefix: str, depth: int,
             ancestors: frozenset[tuple[str, str]]) -> list[dict[str, Any]]:
        nonlocal visited
        entries = [
            item for item in current_provider.iter_entries()
            if item.get("mode") == "160000" and item.get("object_type") == "commit"
        ]
        records: list[dict[str, Any]] = []
        for entry in entries:
            path = f"{prefix}/{entry['path']}" if prefix else entry["path"]
            expected = str(entry["git_object_oid"])
            base = {"path": path, "expected_commit_oid": expected}
            supplied = repositories.get(path)
            if supplied is None:
                records.append({**base, "status": "NOT_SUPPLIED",
                                "reason": "submodule_repository_not_supplied",
                                "recursive_content_verified": False})
                continue
            if depth >= max_depth:
                records.append({**base, "status": "BUDGET_EXCEEDED",
                                "reason": "submodule_max_depth_exceeded",
                                "recursive_content_verified": False})
                continue
            root = Path(supplied).expanduser()
            try:
                root = root.resolve(strict=True)
                if not root.is_dir():
                    raise SubmoduleAccountingError("submodule_repository_not_directory")
                actual = _git(root, "rev-parse", "--verify", "HEAD^{commit}")
                if actual != expected:
                    raise SubmoduleAccountingError("submodule_commit_mismatch")
                identity = (str(root), expected)
                if identity in ancestors:
                    raise SubmoduleAccountingError("submodule_cycle_detected")
                visited += 1
                if visited > max_repositories:
                    raise SubmoduleAccountingError("submodule_repository_budget_exceeded")
                child_provider = _verified_provider(root, expected)
                # Import lazily to avoid a module cycle; child scan uses the same strict
                # pointer parser and optional explicit cache policy as the superproject.
                from audit_engine.semantic_audit.ae32c.lfs_payload_verifier import verify_lfs_payloads
                child_lfs = verify_lfs_payloads(child_provider, stores.get(path))
                nested = walk(child_provider, path, depth + 1, ancestors | {identity})
                nested_scan_complete = all(
                    item.get("status") == "SCANNED"
                    and item.get("recursive_scan_complete") is True for item in nested
                )
                nested_content_verified = all(
                    item.get("recursive_content_verified") is True for item in nested
                )
                records.append({
                    **base, "status": "SCANNED",
                    "child_source_snapshot_id": child_provider.snapshot_identity()["source_snapshot_id"],
                    "child_lfs_attestation_sha256": child_lfs["attestation_sha256"],
                    "child_lfs_status": child_lfs["status"],
                    "child_lfs_pointer_count": child_lfs["pointer_count"],
                    "child_lfs_verified_payload_count": child_lfs["verified_payload_count"],
                    "child_lfs_unverified_payload_count": child_lfs["unverified_payload_count"],
                    "nested_gitlink_count": len(nested), "nested": nested,
                    "recursive_scan_complete": nested_scan_complete,
                    "recursive_content_verified": (
                        child_lfs["lfs_payload_verified"] and nested_content_verified
                    ),
                })
            except (OSError, ValueError, KeyError, RuntimeError) as exc:
                reason = str(exc) if isinstance(exc, SubmoduleAccountingError) else "submodule_repository_unreadable"
                records.append({**base, "status": "UNVERIFIED", "reason": reason[:160],
                                "recursive_content_verified": False})
        return sorted(records, key=lambda item: item["path"].encode("utf-8"))

    identity = provider.snapshot_identity()
    records = walk(provider, "", 0, frozenset())
    payload = {
        "schema": "ae32c/submodule-lfs-accounting/v1",
        "source_snapshot_id": identity["source_snapshot_id"],
        "commit_oid": identity["commit_oid"],
        "source_inventory_sha256": identity["source_inventory_sha256"],
        "gitlink_count": len(records),
        "scanned_repository_count": visited,
        "recursive_scan_complete": all(
            item.get("status") == "SCANNED" and item.get("recursive_scan_complete") is True
            for item in records
        ),
        "recursive_content_verified": all(
            item.get("recursive_content_verified") is True for item in records
        ),
        "records": records,
        "network_accessed": False,
        "credentials_used": False,
        "implicit_checkout_performed": False,
    }
    payload["accounting_sha256"] = _digest(payload)
    return payload
