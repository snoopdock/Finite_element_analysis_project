"""Verify Git LFS payloads and emit complete, source-bound pointer attestations."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any


class LfsPayloadVerificationError(RuntimeError):
    """The committed LFS pointer or supplied local payload store is invalid."""


_POINTER_VERSION = b"version https://git-lfs.github.com/spec/v1"
_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/"
_OID_RE = re.compile(r"sha256:([0-9a-f]{64})\Z")
_KEY_RE = re.compile(r"[a-z0-9.-]+\Z")
_EXT_RE = re.compile(r"ext-[0-9]+-[A-Za-z0-9_-]+\Z")
_MAX_POINTER_BYTES = 1024
_CHUNK_SIZE = 1024 * 1024


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _seal(report: dict[str, Any]) -> dict[str, Any]:
    payload = {key: value for key, value in report.items() if key != "attestation_sha256"}
    report["attestation_sha256"] = hashlib.sha256(_canonical_bytes(payload)).hexdigest()
    return report


def parse_lfs_pointer(data: bytes) -> dict[str, Any]:
    """Parse a canonical v1 pointer conservatively; reject ambiguous encodings."""
    if not isinstance(data, bytes) or not data or len(data) >= _MAX_POINTER_BYTES:
        raise LfsPayloadVerificationError("lfs_pointer_size_invalid")
    if not data.endswith(b"\n") or b"\r" in data or b"\0" in data:
        raise LfsPayloadVerificationError("lfs_pointer_line_ending_invalid")
    try:
        lines = data.decode("ascii", errors="strict").splitlines()
    except UnicodeDecodeError as exc:
        raise LfsPayloadVerificationError("lfs_pointer_encoding_invalid") from exc
    if not lines or lines[0].encode("ascii") != _POINTER_VERSION:
        raise LfsPayloadVerificationError("lfs_pointer_version_unsupported")
    fields: dict[str, str] = {}
    keys: list[str] = []
    for line in lines[1:]:
        if line.count(" ") != 1:
            raise LfsPayloadVerificationError("lfs_pointer_field_invalid")
        key, value = line.split(" ", 1)
        if not _KEY_RE.fullmatch(key) or not value or key in fields:
            raise LfsPayloadVerificationError("lfs_pointer_field_invalid")
        if key not in {"oid", "size"} and not _EXT_RE.fullmatch(key):
            raise LfsPayloadVerificationError("lfs_pointer_extension_invalid")
        fields[key] = value
        keys.append(key)
    if keys != sorted(keys) or not {"oid", "size"}.issubset(fields):
        raise LfsPayloadVerificationError("lfs_pointer_fields_noncanonical")
    match = _OID_RE.fullmatch(fields["oid"])
    if not match:
        raise LfsPayloadVerificationError("lfs_pointer_oid_invalid")
    if not re.fullmatch(r"0|[1-9][0-9]*", fields["size"]):
        raise LfsPayloadVerificationError("lfs_pointer_size_field_invalid")
    return {"oid": match.group(1), "size": int(fields["size"]),
            "extensions": {key: value for key, value in fields.items()
                           if key not in {"oid", "size"}}}


def _safe_object_path(root: Path, oid: str) -> Path:
    candidate = root / oid[:2] / oid[2:4] / oid
    current = root
    for component in (oid[:2], oid[2:4], oid):
        current = current / component
        try:
            info = current.lstat()
        except FileNotFoundError as exc:
            raise LfsPayloadVerificationError("lfs_payload_missing:" + oid) from exc
        if stat.S_ISLNK(info.st_mode):
            raise LfsPayloadVerificationError("lfs_payload_symlink_rejected:" + oid)
    try:
        if not candidate.resolve(strict=True).is_relative_to(root):
            raise LfsPayloadVerificationError("lfs_payload_path_escape:" + oid)
    except (OSError, RuntimeError) as exc:
        raise LfsPayloadVerificationError("lfs_payload_path_invalid:" + oid) from exc
    return candidate


def _hash_payload(path: Path, oid: str, expected_size: int) -> dict[str, Any]:
    before = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode):
        raise LfsPayloadVerificationError("lfs_payload_not_regular_file:" + oid)
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise LfsPayloadVerificationError("lfs_payload_changed_before_read:" + oid)
            while True:
                chunk = handle.read(_CHUNK_SIZE)
                if not chunk:
                    break
                size += len(chunk)
                if size > expected_size:
                    raise LfsPayloadVerificationError("lfs_payload_size_mismatch:" + oid)
                digest.update(chunk)
            after_fd = os.fstat(handle.fileno())
        after_path = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise LfsPayloadVerificationError("lfs_payload_read_failed:" + oid) from exc
    identity_before = (before.st_dev, before.st_ino, before.st_size,
                       before.st_mtime_ns, before.st_ctime_ns)
    identity_fd = (after_fd.st_dev, after_fd.st_ino, after_fd.st_size,
                   after_fd.st_mtime_ns, after_fd.st_ctime_ns)
    identity_path = (after_path.st_dev, after_path.st_ino, after_path.st_size,
                     after_path.st_mtime_ns, after_path.st_ctime_ns)
    if identity_before != identity_fd or identity_fd != identity_path:
        raise LfsPayloadVerificationError("lfs_payload_changed_during_read:" + oid)
    if size != expected_size:
        raise LfsPayloadVerificationError("lfs_payload_size_mismatch:" + oid)
    actual = digest.hexdigest()
    if actual != oid:
        raise LfsPayloadVerificationError("lfs_payload_sha256_mismatch:" + oid)
    return {"oid": oid, "expected_size": expected_size, "actual_size": size,
            "sha256": actual, "status": "VERIFIED_LOCAL_PAYLOAD"}


def verify_lfs_payloads(provider: Any,
                        object_store_root: str | Path | None = None) -> dict[str, Any]:
    """Scan every committed regular blob; optionally verify pointers in an explicit cache.

    No network lookup, Git LFS smudge, credential use, or implicit cache discovery occurs.
    Without a cache, every discovered pointer receives an explicit UNVERIFIED record.
    """
    root = None
    if object_store_root is not None:
        root = Path(object_store_root).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise LfsPayloadVerificationError("lfs_object_store_not_directory")

    regular_inventory: list[dict[str, Any]] = []
    pointers: list[dict[str, Any]] = []
    scanned = 0
    for entry in provider.iter_entries():
        if (entry.get("object_type") != "blob"
                or entry.get("mode") not in {"100644", "100755"}):
            continue
        raw = provider.read_entry(entry["path"])
        scanned += 1
        is_candidate = raw.startswith(_POINTER_PREFIX)
        regular_inventory.append({
            "path": entry["path"],
            "git_object_oid": entry["git_object_oid"],
            "content_sha256": entry["content_sha256"],
            "is_lfs_pointer": is_candidate,
        })
        if not is_candidate:
            continue
        pointer_sha256 = hashlib.sha256(raw).hexdigest()
        base = {
            "path": entry["path"],
            "git_object_oid": entry["git_object_oid"],
            "pointer_sha256": pointer_sha256,
        }
        try:
            parsed = parse_lfs_pointer(raw)
            base.update({"oid": parsed["oid"], "expected_size": parsed["size"]})
            if root is None:
                raise LfsPayloadVerificationError("lfs_object_store_not_supplied")
            payload_path = _safe_object_path(root, parsed["oid"])
            base.update(_hash_payload(payload_path, parsed["oid"], parsed["size"]))
        except LfsPayloadVerificationError as exc:
            base.update({"status": "UNVERIFIED", "reason": str(exc)})
        pointers.append(base)

    regular_inventory.sort(key=lambda item: item["path"].encode("utf-8"))
    pointers.sort(key=lambda item: item["path"].encode("utf-8"))
    verified_count = sum(item.get("status") == "VERIFIED_LOCAL_PAYLOAD" for item in pointers)
    unverified_count = len(pointers) - verified_count
    if root is None:
        status = "NOT_SUPPLIED"
        object_store_mode = "NOT_SUPPLIED_NO_NETWORK"
    elif unverified_count:
        status = "UNVERIFIED"
        object_store_mode = "EXPLICIT_LOCAL_CACHE_NO_NETWORK"
    else:
        status = "VERIFIED_LOCAL_PAYLOADS"
        object_store_mode = "EXPLICIT_LOCAL_CACHE_NO_NETWORK"
    identity = provider.snapshot_identity()
    report = {
        "schema": "ae32c/lfs-payload-verification/v2",
        "source_snapshot_id": identity["source_snapshot_id"],
        "commit_oid": identity["commit_oid"],
        "source_inventory_sha256": identity["source_inventory_sha256"],
        "object_store_mode": object_store_mode,
        "status": status,
        "scan_complete": True,
        "scanned_regular_blob_count": scanned,
        "regular_blob_inventory": regular_inventory,
        "pointer_count": len(pointers),
        "verified_payload_count": verified_count,
        "unverified_payload_count": unverified_count,
        "lfs_payload_verified": status == "VERIFIED_LOCAL_PAYLOADS",
        "records": pointers,
        "remote_payload_provenance_verified": False,
        "atomic_snapshot_established": False,
        "production_approval": False,
    }
    return _seal(report)
