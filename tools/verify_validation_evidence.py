"""Verify detached report digest and the report's referenced evidence files.

This is an integrity check, not a digital signature or independent attestation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(evidence: Path, *, require_pass: bool = False) -> dict:
    root = evidence.resolve(strict=True)
    report = root / "validation_report.json"
    checksum = root / "validation_report.sha256"
    line = checksum.read_text(encoding="utf-8").strip()
    match = re.fullmatch(r"([0-9a-f]{64})  validation_report\.json", line)
    if not match or match.group(1) != sha256_file(report):
        raise ValueError("Report digest mismatch or invalid detached digest file")
    data = json.loads(report.read_text(encoding="utf-8"))
    if data.get("schema_version") != "1.0" or data.get("status") not in ("passed", "failed", "error"):
        raise ValueError("Report schema or status invalid")
    results = data.get("results")
    if not isinstance(results, dict):
        raise ValueError("Missing results")
    for entry in results.values():
        if not isinstance(entry, dict):
            raise ValueError("Malformed test result")
        for name in ("log", "junit"):
            record = entry.get(name)
            if record is None:
                continue
            if not isinstance(record, dict):
                raise ValueError(f"Malformed {name} record")
            relative = record.get("path")
            if not isinstance(relative, str) or not relative or "/" in relative or "\\" in relative or relative in (".", ".."):
                raise ValueError("Unsafe evidence filename")
            path = root / relative
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
                raise ValueError("Missing or unsafe evidence file")
            if sha256_file(path) != record.get("sha256") or path.stat().st_size != record.get("size_bytes"):
                raise ValueError(f"Artifact digest/size mismatch: {relative}")
    if require_pass and data["status"] != "passed":
        raise ValueError(f"Tests did not pass: {data['status']}")
    return data


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--evidence-dir", required=True)
    p.add_argument("--require-pass", action="store_true")
    args = p.parse_args()
    try:
        info = verify(Path(args.evidence_dir), require_pass=args.require_pass)
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as e:
        print(f"Evidence invalid: {e}", file=sys.stderr)
        return 1
    print(f"Evidence verified (digest integrity): {info['status']}, profile={info['profile_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
