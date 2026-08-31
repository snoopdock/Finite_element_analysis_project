#!/usr/bin/env python3
"""Bounded corrective planning for scientific verification feedback."""

from __future__ import annotations

import re
from typing import Dict, List


_QUERY_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "with",
    "is", "are", "was", "were", "be", "this", "that", "these", "those",
    "from", "by", "as", "it", "its", "can", "may", "could", "would",
}


def _terms(text: str, limit: int = 10) -> List[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", str(text or "").lower())
    result: List[str] = []
    seen = set()
    for word in words:
        if word in _QUERY_STOP or word in seen:
            continue
        seen.add(word)
        result.append(word)
        if len(result) >= limit:
            break
    return result


def build_targeted_query(report: Dict) -> str:
    """Build a deterministic evidence query from an evidence gap or conflict."""
    claim = str(report.get("claim", "")).strip()
    reason = str(report.get("reason", "")).strip()
    terms = _terms(claim, limit=8)
    if not terms:
        terms = _terms(reason, limit=8)
    return " ".join(terms)[:220].strip()


def _proposition_ids(report: Dict) -> List[str]:
    values = report.get("proposition_ids", [])
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        values = []
    result = []
    seen = set()
    for value in values:
        value = str(value).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def build_perspective_job(report: Dict) -> Dict:
    """Create a comparison job for an apparent scientific disagreement."""
    return {
        "action": "analyze_perspectives",
        "section_id": report.get("section_id"),
        "paragraph_index": report.get("paragraph_index"),
        "claim": str(report.get("claim", "")),
        "reason": str(report.get("reason", "")),
        "citation_ids": [str(value) for value in report.get("citation_ids", []) if value],
        "proposition_ids": _proposition_ids(report),
        "source_reports": list(report.get("sources", [])) if isinstance(report.get("sources", []), list) else [],
        "confidence": _bounded_confidence(report.get("confidence", 0.0)),
    }


def build_rewrite_job(report: Dict) -> Dict:
    """Create a rewrite job only when verification explicitly justifies rewriting."""
    return {
        "action": "rewrite_and_reverify",
        "section_id": report.get("section_id"),
        "paragraph_index": report.get("paragraph_index"),
        "claim": str(report.get("claim", "")),
        "reason": str(report.get("reason", "")),
        "citation_ids": [str(value) for value in report.get("citation_ids", []) if value],
        "proposition_ids": _proposition_ids(report),
        "source_reports": list(report.get("sources", [])) if isinstance(report.get("sources", []), list) else [],
        "confidence": _bounded_confidence(report.get("confidence", 0.0)),
    }


def _bounded_confidence(value: object) -> float:
    try:
        value = float(value or 0.0)
    except (TypeError, ValueError):
        value = 0.0
    return max(0.0, min(1.0, value))


def plan_corrections(
    review: Dict,
    *,
    max_queries: int = 2,
    max_rewrites: int = 0,
    max_perspective_jobs: int = 2,
) -> Dict:
    """Create bounded research, perspective, and explicitly justified rewrite plans."""
    reports = review.get("reports", []) if isinstance(review, dict) else []
    if not isinstance(reports, list):
        reports = []

    evidence_queries: List[Dict] = []
    perspective_jobs: List[Dict] = []
    rewrite_jobs: List[Dict] = []
    seen_queries = set()

    for report in reports:
        if not isinstance(report, dict):
            continue

        judgment = str(report.get("judgment", "insufficient_evidence")).lower()
        conflict = bool(report.get("source_conflict", False))

        if judgment == "insufficient_evidence":
            query = build_targeted_query(report)
            if query and query.lower() not in seen_queries and len(evidence_queries) < max(0, int(max_queries)):
                seen_queries.add(query.lower())
                evidence_queries.append({
                    "section_id": report.get("section_id"),
                    "query": query,
                    "reason": str(report.get("reason", "")),
                })

        if judgment == "contradicted" or conflict:
            if len(perspective_jobs) < max(0, int(max_perspective_jobs)):
                perspective_jobs.append(build_perspective_job(report))

        # Rewriting is intentionally opt-in at the report level. A plain
        # contradiction never authorizes deletion of a scientific perspective.
        if report.get("rewrite_justified") is True and len(rewrite_jobs) < max(0, int(max_rewrites)):
            rewrite_jobs.append(build_rewrite_job(report))

    return {
        "evidence_queries": evidence_queries,
        "perspective_jobs": perspective_jobs,
        "rewrite_jobs": rewrite_jobs,
        "query_count": len(evidence_queries),
        "perspective_count": len(perspective_jobs),
        "rewrite_count": len(rewrite_jobs),
    }
