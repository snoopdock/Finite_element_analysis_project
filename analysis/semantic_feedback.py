#!/usr/bin/env python3
"""Deterministic feedback policy for semantic verification results."""

from __future__ import annotations

from typing import Dict, List


_VALID = {"supported", "contradicted", "insufficient_evidence"}


def classify_review(report: Dict) -> Dict:
    """Map one semantic review report to a conservative control signal."""
    judgment = str(report.get("judgment", "insufficient_evidence")).lower()
    if judgment not in _VALID:
        judgment = "insufficient_evidence"

    confidence = report.get("confidence", 0.0)
    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence = 0.0

    conflict = bool(report.get("source_conflict", False))

    if conflict:
        action = "seek_more_evidence"
        severity = "high"
    elif judgment == "contradicted":
        action = "rewrite_and_reverify"
        severity = "high" if confidence >= 0.70 else "medium"
    elif judgment == "insufficient_evidence":
        action = "seek_more_evidence"
        severity = "medium" if confidence >= 0.50 else "low"
    else:
        action = "retain"
        severity = "low"

    return {
        "action": action,
        "severity": severity,
        "judgment": judgment,
        "confidence": round(confidence, 4),
        "source_conflict": conflict,
        "reason": str(report.get("reason", "")),
    }


def build_section_feedback(review: Dict) -> Dict[str, Dict]:
    """Aggregate claim-level signals by stable section UUID."""
    result: Dict[str, Dict] = {}

    for report in review.get("reports", []) if isinstance(review, dict) else []:
        if not isinstance(report, dict):
            continue
        section_id = report.get("section_id")
        if not section_id:
            continue

        signal = classify_review(report)
        existing = result.setdefault(
            str(section_id),
            {
                "action": "retain",
                "severity": "low",
                "confidence": 0.0,
                "judgments": [],
                "claims_checked": 0,
                "reasons": [],
            },
        )

        existing["judgments"].append(signal["judgment"])
        existing["claims_checked"] += 1
        existing["confidence"] = max(
            existing["confidence"],
            signal["confidence"],
        )
        if signal["reason"]:
            existing["reasons"].append(signal["reason"])

        rank = {
            "retain": 0,
            "seek_more_evidence": 1,
            "rewrite_and_reverify": 2,
        }
        if rank[signal["action"]] > rank[existing["action"]]:
            existing["action"] = signal["action"]

        severity_rank = {"low": 0, "medium": 1, "high": 2}
        if severity_rank[signal["severity"]] > severity_rank[existing["severity"]]:
            existing["severity"] = signal["severity"]

    return result


def attach_feedback(
    sections: List[Dict],
    review: Dict,
) -> List[Dict]:
    """Return sections annotated with latest semantic feedback."""
    by_id = build_section_feedback(review)
    updated = []

    for section in sections or []:
        if not isinstance(section, dict):
            continue
        clone = dict(section)
        section_id = clone.get("section_id")
        feedback = by_id.get(str(section_id)) if section_id else None
        if feedback:
            clone["semantic_feedback"] = feedback
        updated.append(clone)

    return updated
