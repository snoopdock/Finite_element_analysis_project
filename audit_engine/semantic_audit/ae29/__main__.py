"""CLI for AE-29 iterative repository audit control.

The CLI works on explicit JSON snapshots and never mutates an authoritative
repository checkout. ``apply-preview`` creates only a candidate snapshot file;
``materialize`` creates a separate staging directory.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audit_engine.semantic_audit.ae24.contracts import canonical
from .controller import (
    IterativeAuditError,
    RepositorySnapshot,
    validate_repair,
    validate_verification,
    validate_decision_record,
    materialize_accepted_snapshot,
)


def _read_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8_000_000:
        raise IterativeAuditError("Missing, oversized or symlinked JSON input")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise IterativeAuditError("Invalid JSON input") from exc
    if not isinstance(value, dict):
        raise IterativeAuditError("JSON input must be an object")
    return value


def _write_json(path: Path, value: dict) -> None:
    if path.exists() or path.is_symlink():
        raise IterativeAuditError("Output must not already exist")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AE-29 iterative repository audit control")
    sub = parser.add_subparsers(dest="action", required=True)

    for action in ("verify-repair", "apply-preview", "verify-verification"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--snapshot", type=Path, required=True)
        cmd.add_argument("--repair", type=Path, required=True)
        if action == "verify-verification":
            cmd.add_argument("--after", type=Path, required=True)
            cmd.add_argument("--verification", type=Path, required=True)
        if action == "apply-preview":
            cmd.add_argument("--output", type=Path, required=True)

    decision = sub.add_parser("verify-decision")
    decision.add_argument("--decision", type=Path, required=True)

    materialize = sub.add_parser("materialize")
    materialize.add_argument("--snapshot", type=Path, required=True)
    materialize.add_argument("--destination", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        if args.action == "verify-decision":
            record = _read_json(args.decision)
            validate_decision_record(record)
            print("AE-29 decision record verified")
            return 0

        snapshot = RepositorySnapshot.from_payload(_read_json(args.snapshot))
        repair = _read_json(args.repair)
        if args.action == "verify-repair":
            validate_repair(snapshot, repair)
            print(f"AE-29 repair verified: {repair['repair_sha256']}")
            return 0

        if args.action == "apply-preview":
            candidate = snapshot.apply(repair)
            _write_json(args.output, candidate.to_payload(include_bytes=True))
            print(f"AE-29 candidate snapshot written: {args.output}")
            return 0

        after = RepositorySnapshot.from_payload(_read_json(args.after))
        verification = _read_json(args.verification)
        validate_verification(snapshot, after, repair, verification)
        print(f"AE-29 verification verified: {verification['verification_sha256']}")
        return 0 if verification["status"] == "passed" else 3

    except (IterativeAuditError, OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, f"AE-29 failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
