"""Verify Git LFS payload bytes against committed pointer OIDs without network access."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import stat
from typing import Any


class LfsPayloadVerificationError(RuntimeError):
    """The committed LFS pointer or supplied local payload store is invalid."""


_POINTER_VERSION = b"version https://git-lfs.github.com/spec/v1"
_OID_RE = re.compile(r"sha256:([0-9a-f]{64})\Z")
_KEY_RE = re.compile(r"[a-z0-9.-]+\Z")
_EXT_RE = re.compile(r"ext-[0-9]+-[A-Za-z0-9_-]+\Z")
_MAX_POINTER_BYTES = 1024
_CHUNK_SIZE = 1024 * 1024


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


def verify_lfs_payloads(provider: Any, object_store_root: str | Path) -> dict[str, Any]:
    """Scan the pinned tree and verify each LFS payload in an explicit local cache."""
    root = Path(object_store_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise LfsPayloadVerificationError("lfs_object_store_not_directory")
    pointers: list[dict[str, Any]] = []
    for entry in provider.iter_entries():
        if entry.get("object_type") != "blob" or entry.get("mode") not in {"100644", "100755"}:
            continue
        raw = provider.read_entry(entry["path"])
        if not raw.startswith(b"version https://git-lfs.github.com/spec/"):
            continue
        try:
            parsed = parse_lfs_pointer(raw)
            payload_path = _safe_object_path(root, parsed["oid"])
            verified = _hash_payload(payload_path, parsed["oid"], parsed["size"])
            pointers.append({"path": entry["path"], **verified})
        except LfsPayloadVerificationError as exc:
            pointers.append({"path": entry["path"], "status": "UNVERIFIED",
                             "reason": str(exc)})
    verified_count = sum(item.get("status") == "VERIFIED_LOCAL_PAYLOAD"
                         for item in pointers)
    failed_count = len(pointers) - verified_count
    identity = provider.snapshot_identity()
    return {
        "schema": "ae32c/lfs-payload-verification/v1",
        "source_snapshot_id": identity["source_snapshot_id"],
        "commit_oid": identity["commit_oid"],
        "source_inventory_sha256": identity["source_inventory_sha256"],
        "object_store_mode": "EXPLICIT_LOCAL_CACHE_NO_NETWORK",
        "pointer_count": len(pointers),
        "verified_payload_count": verified_count,
        "unverified_payload_count": failed_count,
        "lfs_payload_verified": failed_count == 0,
        "records": pointers,
        "remote_payload_provenance_verified": False,
        "atomic_snapshot_established": False,
        "production_approval": False,
    }
