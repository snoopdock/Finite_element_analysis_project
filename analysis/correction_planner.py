#!/usr/bin/env python3
"""Bounded corrective-action planning for semantic verification feedback."""

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
    """Build one deterministic evidence query from an unsupported/conflicted claim."""
    claim = str(report.get("claim", "")).strip()
    reason = str(report.get("reason", "")).strip()
    terms = _terms(claim, limit=8)

    if not terms:
        terms = _terms(reason, limit=8)

    query = " ".join(terms)
    return query[:220].strip()


def build_rewrite_job(report: Dict) -> Dict:
    """Build a bounded rewrite job from one contradicted claim."""
    return {
        "action": "rewrite_and_reverify",
        "section_id": report.get("section_id"),
        "paragraph_index": report.get("paragraph_index"),
        "claim": str(report.get("claim", "")),
        "reason": str(report.get("reason", "")),
        "citation_ids": [
            str(value)
            for value in report.get("citation_ids", [])
            if value
        ],
        "source_reports": list(
            report.get("sources", [])
            if isinstance(report.get("sources", []), list)
            else []
        ),
        "confidence": max(
            0.0,
            min(1.0, float(report.get("confidence", 0.0) or 0.0)),
        ),
    }


def plan_corrections(
    review: Dict,
    *,
    max_queries: int = 2,
    max_rewrites: int = 1,
) -> Dict:
    """Create bounded evidence-query and rewrite plans without executing them."""
    reports = review.get("reports", []) if isinstance(review, dict) else []
    if not isinstance(reports, list):
        reports = []

    evidence_queries: List[Dict] = []
    rewrite_jobs: List[Dict] = []
    seen_queries = set()

    for report in reports:
        if not isinstance(report, dict):
            continue

        judgment = str(report.get("judgment", "insufficient_evidence")).lower()
        conflict = bool(report.get("source_conflict", False))

        if judgment == "insufficient_evidence" or conflict:
            query = build_targeted_query(report)
            if query and query.lower() not in seen_queries and len(evidence_queries) < max(0, int(max_queries)):
                seen_queries.add(query.lower())
                evidence_queries.append({
                    "section_id": report.get("section_id"),
                    "query": query,
                    "reason": str(report.get("reason", "")),
                })

        elif judgment == "contradicted" and len(rewrite_jobs) < max(0, int(max_rewrites)):
            rewrite_jobs.append(build_rewrite_job(report))

    return {
        "evidence_queries": evidence_queries,
        "rewrite_jobs": rewrite_jobs,
        "query_count": len(evidence_queries),
        "rewrite_count": len(rewrite_jobs),
    }
