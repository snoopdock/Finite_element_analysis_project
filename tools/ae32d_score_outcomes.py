#!/usr/bin/env python3
"""Deterministic AE-32D categorical outcome classifier.

This module classifies already-produced audit outcomes against adjudicated labels.
It does not infer ground truth, evaluate semantic evidence, or replace review.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

GROUND_TRUTH = {"confirmed_defect", "no_defect", "ambiguous", "pending_adjudication"}
AUDIT_OUTCOMES = {"defect_detected", "no_defect", "abstain"}
CATEGORIES = (
    "correct_detection",
    "missed_defect",
    "false_positive",
    "correct_no_defect",
    "correct_abstention",
    "incorrect_abstention",
    "not_scorable",
)


def classify_outcome(
    ground_truth: str,
    audit_outcome: str | None,
    *,
    provenance_valid: bool,
) -> dict[str, Any]:
    """Return one rubric category; malformed or untrusted trials are not scorable."""
    if ground_truth not in GROUND_TRUTH:
        raise ValueError("unknown_ground_truth_label")
    if audit_outcome is not None and audit_outcome not in AUDIT_OUTCOMES:
        raise ValueError("unknown_audit_outcome")
    if not isinstance(provenance_valid, bool):
        raise TypeError("provenance_valid_must_be_boolean")

    if not provenance_valid or audit_outcome is None or ground_truth == "pending_adjudication":
        category = "not_scorable"
    elif ground_truth == "confirmed_defect":
        category = {
            "defect_detected": "correct_detection",
            "no_defect": "missed_defect",
            "abstain": "incorrect_abstention",
        }[audit_outcome]
    elif ground_truth == "no_defect":
        category = {
            "defect_detected": "false_positive",
            "no_defect": "correct_no_defect",
            "abstain": "incorrect_abstention",
        }[audit_outcome]
    else:  # ambiguous
        category = (
            "correct_abstention" if audit_outcome == "abstain" else "false_positive"
        )

    return {
        "ground_truth": ground_truth,
        "audit_outcome": audit_outcome,
        "provenance_valid": provenance_valid,
        "category": category,
        "primary_score_eligible": category != "not_scorable",
    }


def summarize_outcomes(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate categories while preserving the raw attempted and scorable counts."""
    counts = Counter()
    for record in records:
        result = classify_outcome(
            record.get("ground_truth"),
            record.get("audit_outcome"),
            provenance_valid=record.get("provenance_valid") is True,
        )
        counts[result["category"]] += 1

    scorable = sum(counts[name] for name in CATEGORIES if name != "not_scorable")
    correct = sum(counts[name] for name in (
        "correct_detection", "correct_no_defect", "correct_abstention"
    ))
    return {
        "schema_version": "ae32d/outcome-summary/v1",
        "attempted_case_count": len(records),
        "scorable_case_count": scorable,
        "not_scorable_case_count": counts["not_scorable"],
        "correct_case_count": correct,
        "case_level_correct_audit_outcome_rate": (
            correct / scorable if scorable else None
        ),
        "categories": {name: counts[name] for name in CATEGORIES},
        "warning": (
            "Descriptive classification only; use only adjudicated ground truth "
            "and frozen rubric for benchmark reporting."
        ),
    }
