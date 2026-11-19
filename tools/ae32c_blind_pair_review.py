#!/usr/bin/env python3
"""Prepare and validate blinded AE-32C paired-diagnosis reviews."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audit_engine.semantic_audit.ae32c.blind_pair_review import (
    BlindReviewError,
    compare_reviews,
    prepare_from_files,
    unblind_pair,
    validate_review_record,
    write_json,
)


def read_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def emit(value: Any, output: str | None = None) -> None:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if output:
        Path(output).write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="Prepare two blinded reviewer packets from an isolated pair")
    prepare.add_argument("--comparison", required=True)
    prepare.add_argument("--control-report", required=True)
    prepare.add_argument("--graph-report", required=True)
    prepare.add_argument("--output-dir", required=True)
    prepare.add_argument("--pair-id")

    validate = sub.add_parser("validate", help="Validate one completed reviewer form")
    validate.add_argument("--packet", required=True)
    validate.add_argument("--review", required=True)

    agreement = sub.add_parser("agreement", help="Compare two independent completed reviews")
    agreement.add_argument("--packet", required=True)
    agreement.add_argument("--reviewer-a", required=True)
    agreement.add_argument("--reviewer-b", required=True)
    agreement.add_argument("--output")

    unblind = sub.add_parser("unblind", help="Reveal A/B mapping after review agreement is recorded")
    unblind.add_argument("--key", required=True)
    unblind.add_argument("--agreement", required=True)
    unblind.add_argument("--output")

    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_from_files(
                args.comparison,
                args.control_report,
                args.graph_report,
                args.output_dir,
                pair_id=args.pair_id,
            )
            emit({"valid": True, **result})
            return 0
        if args.command == "validate":
            packet = read_json(args.packet)
            review = read_json(args.review)
            result = validate_review_record(review, packet)
            emit(result)
            return 0 if result["valid"] else 2
        if args.command == "agreement":
            packet = read_json(args.packet)
            first = read_json(args.reviewer_a)
            second = read_json(args.reviewer_b)
            result = compare_reviews(packet, first, second)
            emit(result, args.output)
            return 0
        key = read_json(args.key)
        agreement_result = read_json(args.agreement)
        result = unblind_pair(key, agreement_result)
        emit(result, args.output)
        return 0
    except (OSError, ValueError, json.JSONDecodeError, BlindReviewError) as exc:
        emit({"valid": False, "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
