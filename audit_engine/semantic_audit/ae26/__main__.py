"""CLI for deterministic semantic projection and contract-diff replay.

Only canonical JSON documents and bounded regular evidence files are read.
No source program is executed and no graph mutation is performed.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import stat
import re

from audit_engine.semantic_audit.ae24.contracts import canonical, ContractError, MAX_BYTES, MAX_SOURCE_BYTES
from .semantics import snapshot, semantic_projection, diff_contracts, SemanticModelError

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _read_regular(path: Path, limit: int) -> bytes:
    path = Path(path)
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ContractError("Symlink evidence path forbidden")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ContractError("Evidence input must be a bounded regular file")
        data = os.read(fd, limit + 1)
        if len(data) != info.st_size:
            raise ContractError("Evidence file changed during read")
        return data
    finally:
        os.close(fd)


def _document(path: Path) -> dict:
    data = _read_regular(path, MAX_BYTES)
    try:
        obj = json.loads(data)
    except (ValueError, UnicodeError) as exc:
        raise ContractError("Malformed JSON evidence") from exc
    if not isinstance(obj, dict) or canonical(obj) != data:
        raise ContractError("Expected canonical JSON object with final newline")
    return obj


def _load(contract_path: Path, evidence_directory: Path):
    doc = _document(contract_path)
    root = Path(evidence_directory)
    if root.is_symlink() or not root.is_dir():
        raise ContractError("Evidence root must be a real directory")
    payload = {}
    for row in doc.get("sources", []):
        sid = row.get("id") if isinstance(row, dict) else None
        if not isinstance(sid, str) or not NAME.fullmatch(sid):
            raise ContractError("Unsafe or invalid source identity")
        if sid in payload:
            raise ContractError("Duplicate source identity")
        payload[sid] = _read_regular(root / sid, MAX_SOURCE_BYTES)
    return doc, payload


def main(argv=None):
    parser = argparse.ArgumentParser(description="AE-26 semantic projection and evolution")
    sub = parser.add_subparsers(dest="action", required=True)
    p_snapshot = sub.add_parser("snapshot")
    p_snapshot.add_argument("--contract", type=Path, required=True)
    p_snapshot.add_argument("--evidence-dir", type=Path, required=True)
    p_diff = sub.add_parser("diff")
    p_diff.add_argument("--before-contract", type=Path, required=True)
    p_diff.add_argument("--before-evidence-dir", type=Path, required=True)
    p_diff.add_argument("--after-contract", type=Path, required=True)
    p_diff.add_argument("--after-evidence-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.action == "snapshot":
        doc, raw = _load(args.contract, args.evidence_dir)
        result = semantic_projection(snapshot(doc, raw))
    else:
        before, before_raw = _load(args.before_contract, args.before_evidence_dir)
        after, after_raw = _load(args.after_contract, args.after_evidence_dir)
        result = diff_contracts(before, before_raw, after, after_raw)
    print(canonical(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
