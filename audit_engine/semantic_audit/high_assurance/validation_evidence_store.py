"""Content-addressed, append-only publication for CI validation evidence.

G3.4.10. This layer *packages* independently generated evidence, checks the
internal byte-level bindings and JUnit counts, and publishes the package
without overwriting a committed object. It does not authenticate a GitHub run,
verify Git commits, or replace the central semantic evidence verifier.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZipInfo, ZIP_STORED, BadZipFile

SHA = re.compile(r"[0-9a-f]{64}\Z")
NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}\Z")
MAX_FILES = 24
MAX_BYTES = 64 * 1024 * 1024
MAX_FILE_BYTES = 32 * 1024 * 1024
SCHEMA = "validation-evidence-cas/v1"
FIXED_ZIP_DATE = (1980, 1, 1, 0, 0, 0)


class EvidenceBundleError(RuntimeError):
    """Evidence integrity or publication safety boundary was violated."""


@dataclass(frozen=True)
class BundleReceipt:
    bundle_sha256: str
    report_sha256: str
    byte_size: int
    committed: bool


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(data: object) -> bytes:
    return (json.dumps(data, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _safe_name(value: object) -> str:
    if not isinstance(value, str) or not NAME.fullmatch(value) or value in (".", ".."):
        raise EvidenceBundleError("Invalid evidence filename")
    return value


def _read_file(folder: Path, name: str, *, max_bytes: int = MAX_FILE_BYTES) -> bytes:
    path = folder / _safe_name(name)
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
    except OSError as exc:
        raise EvidenceBundleError(f"Cannot open evidence member: {name}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
            raise EvidenceBundleError(f"Unsafe or oversized evidence member: {name}")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            content = handle.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise EvidenceBundleError(f"Oversized evidence member: {name}")
        return content
    finally:
        os.close(fd)


def _junit_counts(xml_bytes: bytes) -> dict[str, int]:
    try:
        root = ET.fromstring(xml_bytes)
        if root.tag == "testsuite":
            suites = [root]
        elif root.tag == "testsuites":
            suites = list(root.findall("testsuite"))
        else:
            raise ValueError("Wrong JUnit document root")
        if not suites:
            raise ValueError("No test suite")
        return {key: sum(int(s.attrib.get(key, "0")) for s in suites)
                for key in ("tests", "failures", "errors", "skipped")}
    except (ValueError, ET.ParseError) as exc:
        raise EvidenceBundleError("Invalid JUnit document") from exc


def _validate_members(files: dict[str, bytes]) -> tuple[str, dict]:
    if "validation_report.json" not in files or "validation_report.sha256" not in files:
        raise EvidenceBundleError("Missing report or detached digest")
    report_raw = files["validation_report.json"]
    report_hash = _sha(report_raw)
    expected_detached = f"{report_hash}  validation_report.json\n".encode("ascii")
    if files["validation_report.sha256"].rstrip(b"\r\n") != expected_detached.rstrip(b"\n"):
        raise EvidenceBundleError("Detached report digest mismatch")
    try:
        report = json.loads(report_raw)
        if not isinstance(report, dict):
            raise TypeError()
    except (ValueError, TypeError) as exc:
        raise EvidenceBundleError("Invalid evidence JSON") from exc
    if report.get("status") not in ("passed", "failed", "error"):
        raise EvidenceBundleError("Unknown evidence outcome")
    if report.get("schema_version") not in ("1.0", "1.1"):
        raise EvidenceBundleError("Unsupported report schema")
    if not isinstance(report.get("profile_id"), str) or not report["profile_id"]:
        raise EvidenceBundleError("Missing profile identity")
    for field in ("target_commit_sha", "engine_commit_sha"):
        if not isinstance(report.get(field), str) or not re.fullmatch(r"[0-9a-f]{40,64}", report[field]):
            raise EvidenceBundleError(f"Missing or invalid {field}")
    declared: set[str] = {"validation_report.json", "validation_report.sha256"}
    def member(record: object) -> tuple[str, bytes]:
        if not isinstance(record, dict):
            raise EvidenceBundleError("Invalid file record")
        name = _safe_name(record.get("path"))
        digest = record.get("sha256")
        length = record.get("size_bytes")
        if name in declared or name not in files:
            raise EvidenceBundleError("Missing or repeated evidence member")
        if not isinstance(digest, str) or not SHA.fullmatch(digest):
            raise EvidenceBundleError("Invalid SHA-256 record")
        if type(length) is not int or length < 0:
            raise EvidenceBundleError("Invalid size record")
        content = files[name]
        if len(content) != length or _sha(content) != digest:
            raise EvidenceBundleError(f"Digest or size mismatch: {name}")
        declared.add(name)
        return name, content

    engine = report.get("engine_unit_tests")
    if isinstance(engine, dict) and engine.get("log") is not None:
        member(engine["log"])
    results = report.get("results")
    if not isinstance(results, dict):
        raise EvidenceBundleError("Missing test results")
    for label in ("targeted", "regression"):
        result = results.get(label)
        if result is None:
            continue
        if not isinstance(result, dict):
            raise EvidenceBundleError("Invalid test result")
        if result.get("log") is not None:
            member(result["log"])
        if result.get("junit") is not None:
            _, xml = member(result["junit"])
            counts = _junit_counts(xml)
            if counts != result.get("counts"):
                raise EvidenceBundleError(f"JUnit counts mismatch: {label}")
            if result.get("status") == "passed" and (
                    counts["failures"] or counts["errors"] or
                    result.get("exit_code") != 0 or counts["tests"] == 0):
                raise EvidenceBundleError(f"Contradictory successful result: {label}")
    if report["status"] == "passed":
        if not isinstance(engine, dict) or engine.get("status") != "passed":
            raise EvidenceBundleError("Report claims success without passed engine tests")
        target_result = results.get("targeted")
        if not isinstance(target_result, dict) or target_result.get("status") != "passed":
            raise EvidenceBundleError("Report claims success without passed targeted tests")
        regression_result = results.get("regression")
        if isinstance(regression_result, dict) and regression_result.get("status") in ("failed", "error"):
            raise EvidenceBundleError("Report claims success despite failed regression")
    if declared != set(files):
        raise EvidenceBundleError("Undeclared evidence files found")
    return report_hash, report


def _collect(folder: Path) -> dict[str, bytes]:
    if folder.is_symlink() or not folder.is_dir():
        raise EvidenceBundleError("Evidence directory must be a real directory")
    names = [item.name for item in folder.iterdir()]
    if not 2 <= len(names) <= MAX_FILES:
        raise EvidenceBundleError("Invalid evidence file count")
    files: dict[str, bytes] = {}
    total = 0
    for name in names:
        content = _read_file(folder, name)
        total += len(content)
        if total > MAX_BYTES:
            raise EvidenceBundleError("Evidence exceeds size policy")
        files[name] = content
    return files


def _deterministic_zip(files: dict[str, bytes], report_hash: str) -> bytes:
    manifest = {
        "schema_version": SCHEMA,
        "report_sha256": report_hash,
        "files": [{"name": name, "sha256": _sha(data), "size_bytes": len(data)}
                  for name, data in sorted(files.items())],
    }
    out = BytesIO()
    all_files = dict(files)
    all_files["bundle_manifest.json"] = _canonical(manifest)
    with ZipFile(out, "w", compression=ZIP_STORED, allowZip64=False) as zipfile:
        for name, data in sorted(all_files.items()):
            info = ZipInfo(name, FIXED_ZIP_DATE)
            info.compress_type = ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100600 << 16
            zipfile.writestr(info, data)
    return out.getvalue()


def inspect_bundle(data: bytes) -> tuple[str, str]:
    if len(data) > MAX_BYTES + 1024 * 1024:
        raise EvidenceBundleError("Bundle size limit exceeded")
    try:
        with ZipFile(BytesIO(data), "r") as zipfile:
            infos = zipfile.infolist()
            names = [entry.filename for entry in infos]
            if not 3 <= len(names) <= MAX_FILES + 1 or len(set(names)) != len(names):
                raise EvidenceBundleError("Missing or repeated archive entries")
            if any(entry.compress_type != ZIP_STORED or
                   entry.file_size > MAX_FILE_BYTES or
                   entry.is_dir() or not NAME.fullmatch(entry.filename) or
                   (entry.create_system == 3 and stat.S_IFMT(entry.external_attr >> 16)
                    not in (0, stat.S_IFREG)) for entry in infos):
                raise EvidenceBundleError("Unsafe archive entry")
            if sum(entry.file_size for entry in infos) > MAX_BYTES:
                raise EvidenceBundleError("Archive uncompressed size limit exceeded")
            members = {entry.filename: zipfile.read(entry) for entry in infos}
    except (BadZipFile, OSError, ValueError) as exc:
        raise EvidenceBundleError("Invalid evidence archive") from exc
    try:
        manifest_raw = members.pop("bundle_manifest.json")
        manifest = json.loads(manifest_raw)
        if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA:
            raise EvidenceBundleError("Unsupported manifest")
        expected = [{"name": name, "sha256": _sha(blob), "size_bytes": len(blob)}
                    for name, blob in sorted(members.items())]
        if manifest.get("files") != expected:
            raise EvidenceBundleError("Bundle member manifest mismatch")
        if _canonical(manifest) != manifest_raw:
            raise EvidenceBundleError("Noncanonical manifest")
        report_hash, _ = _validate_members(members)
        if manifest.get("report_sha256") != report_hash:
            raise EvidenceBundleError("Report binding mismatch")
        return _sha(data), report_hash
    except (KeyError, TypeError, ValueError) as exc:
        raise EvidenceBundleError("Invalid bundle manifest") from exc


class EvidenceBundleStore:
    """Append-only CAS of deterministic evidence ZIPs, scoped to a trusted root."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        if self.root.is_symlink():
            raise EvidenceBundleError("Store root is a symlink")
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.root.is_dir() or self.root.is_symlink():
            raise EvidenceBundleError("Unsafe evidence store root")

    def _target(self, digest: str) -> Path:
        if not isinstance(digest, str) or not SHA.fullmatch(digest):
            raise EvidenceBundleError("Invalid evidence bundle digest")
        return self.root / f"{digest}.validation.zip"

    def _read_target(self, path: Path) -> bytes:
        return _read_file(self.root, path.name, max_bytes=MAX_BYTES + 1024 * 1024)

    def verify(self, digest: str) -> BundleReceipt:
        target = self._target(digest)
        data = self._read_target(target)
        found_digest, report_hash = inspect_bundle(data)
        if found_digest != digest:
            raise EvidenceBundleError("Content-address mismatch")
        return BundleReceipt(digest, report_hash, len(data), False)

    def publish(self, evidence_directory: str | Path) -> BundleReceipt:
        files = _collect(Path(evidence_directory))
        report_hash, _ = _validate_members(files)
        data = _deterministic_zip(files, report_hash)
        digest, checked_report = inspect_bundle(data)
        if checked_report != report_hash:
            raise EvidenceBundleError("Internal report binding error")
        target = self._target(digest)
        fd, temp = tempfile.mkstemp(prefix=".validation-", suffix=".tmp", dir=self.root)
        committed = False
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                # Hard-link creates the fully fsynced file atomically and fails
                # if another writer has already committed that name. Unlike
                # os.replace, it NEVER overwrites a pre-existing artifact.
                os.link(temp, target)
                committed = True
            except FileExistsError:
                self.verify(digest)
            if hasattr(os, "O_DIRECTORY"):
                dirfd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(dirfd)
                finally:
                    os.close(dirfd)
        finally:
            try:
                os.unlink(temp)
            except FileNotFoundError:
                pass
        return BundleReceipt(digest, report_hash, len(data), committed)
