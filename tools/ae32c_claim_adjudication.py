#!/usr/bin/env python3
"""Create, validate, and compare AE-32C human claim-adjudication records."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audit_engine.semantic_audit.ae32c.claim_evidence import (
    build_adjudication_template,
    compute_inter_rater_agreement,
    validate_adjudication_record,
)


def _read_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(value: Any, path: str | None) -> None:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if path:
        Path(path).write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)


def _assessment(report: Any) -> dict[str, Any]:
    if not isinstance(report, dict) or not isinstance(report.get("claim_evidence_assessment"), dict):
        raise ValueError("report_claim_evidence_assessment_missing")
    assessment = report["claim_evidence_assessment"]
    if assessment.get("status") != "available" or not assessment.get("items"):
        raise ValueError("report_has_no_adjudicable_claims")
    return assessment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    template_parser = sub.add_parser("template", help="Create a blank reviewer record from a report JSON")
    template_parser.add_argument("report")
    template_parser.add_argument("--output")

    validate_parser = sub.add_parser("validate", help="Validate one reviewer record against a report")
    validate_parser.add_argument("report")
    validate_parser.add_argument("review")

    agreement_parser = sub.add_parser("agreement", help="Validate two reviews and compute agreement")
    agreement_parser.add_argument("report")
    agreement_parser.add_argument("reviewer_a")
    agreement_parser.add_argument("reviewer_b")
    agreement_parser.add_argument("--output")

    args = parser.parse_args(argv)
    try:
        report = _read_json(args.report)
        assessment = _assessment(report)
        if args.command == "template":
            template = build_adjudication_template(assessment, str(report.get("investigation_id", "unknown")))
            _write_json(template, args.output)
            return 0
        if args.command == "validate":
            review = _read_json(args.review)
            result = validate_adjudication_record(review, assessment)
            _write_json(result, None)
            return 0 if result["valid"] else 2
        first = _read_json(args.reviewer_a)
        second = _read_json(args.reviewer_b)
        first_result = validate_adjudication_record(first, assessment)
        second_result = validate_adjudication_record(second, assessment)
        if not first_result["valid"] or not second_result["valid"]:
            _write_json({"valid": False, "reviewer_a": first_result, "reviewer_b": second_result}, args.output)
            return 2
        agreement = compute_inter_rater_agreement(first, second)
        _write_json({"valid": True, "agreement": agreement}, args.output)
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _write_json({"valid": False, "error": str(exc)}, None)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
