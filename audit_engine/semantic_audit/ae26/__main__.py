"""Manual, read-only, bounded AE-26 semantic snapshot and evolution CLI.

Usage:
  python -m audit_engine.semantic_audit.ae26 snapshot \
      --contract CONTRACT.json --evidence-dir evidence/
  python -m audit_engine.semantic_audit.ae26 verify-snapshot \
      --contract CONTRACT.json --evidence-dir evidence/ --snapshot SNAPSHOT.json
  python -m audit_engine.semantic_audit.ae26 diff \
      --before-contract BEFORE.json --before-evidence-dir before-evidence/ \
      --after-contract AFTER.json --after-evidence-dir after-evidence/
  python -m audit_engine.semantic_audit.ae26 verify-diff \
      --before-contract BEFORE.json --before-evidence-dir before-evidence/ \
      --after-contract AFTER.json --after-evidence-dir after-evidence/ \
      --report DIFF.json

The CLI never executes source programs, mutates the SemanticGraph, contacts
external services, or promotes candidate relationships.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import os
import stat

from audit_engine.semantic_audit.ae24.contracts import (
    canonical,
    ContractError,
    MAX_BYTES,
)
from audit_engine.semantic_audit.ae25.__main__ import load_inputs
from .semantics import (
    diff_contracts,
    semantic_projection,
    snapshot,
    verify_diff,
    verify_projection,
)


def _read_regular_claim(path: Path) -> bytes:
    path = Path(path)
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ContractError("Claim evidence path forbidden")
    try:
        fd = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
        )
    except OSError as exc:
        raise ContractError("Unable to open claim file") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise ContractError("Claim input must be a bounded regular file")
        data = os.read(fd, MAX_BYTES + 1)
        if len(data) != info.st_size:
            raise ContractError("Claim file changed during read")
        return data
    finally:
        os.close(fd)


def _load_json_document(path: Path) -> dict:
    """Read a bounded canonical JSON object for replay claims."""
    data = _read_regular_claim(path)
    try:
        obj = json.loads(data)
    except (ValueError, UnicodeError) as exc:
        raise ContractError("Malformed JSON claim") from exc
    if not isinstance(obj, dict) or canonical(obj) != data:
        raise ContractError("Expected canonical JSON object with final newline")
    return obj


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="AE-26 bounded semantic identity and evolution"
    )
    sub = parser.add_subparsers(dest="action", required=True)

    p_snapshot = sub.add_parser("snapshot")
    p_snapshot.add_argument("--contract", type=Path, required=True)
    p_snapshot.add_argument("--evidence-dir", type=Path, required=True)

    p_verify_snapshot = sub.add_parser("verify-snapshot")
    p_verify_snapshot.add_argument("--contract", type=Path, required=True)
    p_verify_snapshot.add_argument("--evidence-dir", type=Path, required=True)
    p_verify_snapshot.add_argument("--snapshot", type=Path, required=True)

    p_diff = sub.add_parser("diff")
    p_diff.add_argument("--before-contract", type=Path, required=True)
    p_diff.add_argument("--before-evidence-dir", type=Path, required=True)
    p_diff.add_argument("--after-contract", type=Path, required=True)
    p_diff.add_argument("--after-evidence-dir", type=Path, required=True)

    p_verify_diff = sub.add_parser("verify-diff")
    p_verify_diff.add_argument("--before-contract", type=Path, required=True)
    p_verify_diff.add_argument("--before-evidence-dir", type=Path, required=True)
    p_verify_diff.add_argument("--after-contract", type=Path, required=True)
    p_verify_diff.add_argument("--after-evidence-dir", type=Path, required=True)
    p_verify_diff.add_argument("--report", type=Path, required=True)

    args = parser.parse_args(argv)

    if args.action == "snapshot":
        doc, evidence = load_inputs(args.contract, args.evidence_dir)
        result = semantic_projection(snapshot(doc, evidence))
    elif args.action == "verify-snapshot":
        doc, evidence = load_inputs(args.contract, args.evidence_dir)
        result = verify_projection(
            doc,
            evidence,
            _load_json_document(args.snapshot),
        )
    elif args.action == "diff":
        before, before_evidence = load_inputs(
            args.before_contract,
            args.before_evidence_dir,
        )
        after, after_evidence = load_inputs(
            args.after_contract,
            args.after_evidence_dir,
        )
        result = diff_contracts(
            before,
            before_evidence,
            after,
            after_evidence,
        )
    else:
        before, before_evidence = load_inputs(
            args.before_contract,
            args.before_evidence_dir,
        )
        after, after_evidence = load_inputs(
            args.after_contract,
            args.after_evidence_dir,
        )
        claimed = _load_json_document(args.report)
        verify_diff(
            before,
            before_evidence,
            after,
            after_evidence,
            claimed,
        )
        result = {
            "status": "source_replayed",
            "report_sha256": claimed["report_sha256"],
            "semantic_diff_fingerprint": claimed["semantic_diff_fingerprint"],
            "before_semantic_fingerprint": claimed["before"]["semantic_fingerprint"],
            "after_semantic_fingerprint": claimed["after"]["semantic_fingerprint"],
            "before_hypothesis_fingerprint": claimed["before"]["hypothesis_fingerprint"],
            "after_hypothesis_fingerprint": claimed["after"]["hypothesis_fingerprint"],
        }

    print(canonical(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
