#!/usr/bin/env python3
"""Document-level semantic evidence review."""

from __future__ import annotations

import re
from typing import Dict, List

from analysis.semantic_verifier import verify_claim


_CITATION_RE = re.compile(
    r"\[([^\[\]\s,]+(?:\s*,\s*[^\[\]\s,]+)*)\]"
)


def _citation_ids(text: str) -> List[str]:
    result = []
    seen = set()
    for group in _CITATION_RE.findall(str(text or "")):
        for value in group.split(","):
            value = value.strip()
            if value and value not in seen:
                seen.add(value)
                result.append(value)
    return result


def review_document_claims(
    sections: List[Dict],
    evidence: List[Dict],
    provider,
    parser,
    *,
    max_claims: int = 4,
    max_sources_per_claim: int = 2,
    max_passages_per_source: int = 2,
    max_passage_chars: int = 1800,
    max_tokens: int = 700,
    model: str | None = None,
) -> Dict:
    """Review cited paragraphs, bounded by a per-cycle claim budget."""
    evidence_by_id = {
        str(item.get("source_id")): dict(item)
        for item in evidence or []
        if isinstance(item, dict) and item.get("source_id")
    }

    reports = []
    considered = 0

    for section in sections or []:
        if considered >= max(0, int(max_claims)):
            break
        if not isinstance(section, dict):
            continue

        section_id = section.get("section_id")
        content = str(section.get("content", ""))
        paragraphs = [
            paragraph.strip()
            for paragraph in re.split(r"\n\s*\n", content)
            if paragraph.strip()
        ]

        for paragraph_index, paragraph in enumerate(paragraphs):
            if considered >= max(0, int(max_claims)):
                break

            citation_ids = _citation_ids(paragraph)
            if not citation_ids:
                continue

            verification = verify_claim(
                paragraph,
                citation_ids,
                evidence_by_id,
                provider,
                parser,
                max_sources=max_sources_per_claim,
                max_passages_per_source=max_passages_per_source,
                max_passage_chars=max_passage_chars,
                max_tokens=max_tokens,
                model=model,
            )

            reports.append({
                "section_id": section_id,
                "paragraph_index": paragraph_index,
                "claim": paragraph,
                "citation_ids": citation_ids,
                **verification,
            })
            considered += 1

            if verification.get("verification_skipped"):
                return {
                    "claims_checked": len(reports),
                    "claims_supported": sum(
                        1 for report in reports
                        if report.get("judgment") == "supported"
                    ),
                    "claims_contradicted": sum(
                        1 for report in reports
                        if report.get("judgment") == "contradicted"
                    ),
                    "claims_insufficient": sum(
                        1 for report in reports
                        if report.get("judgment") == "insufficient_evidence"
                    ),
                    "verification_skipped": True,
                    "reports": reports,
                }

    return {
        "claims_checked": len(reports),
        "claims_supported": sum(
            1 for report in reports
            if report.get("judgment") == "supported"
        ),
        "claims_contradicted": sum(
            1 for report in reports
            if report.get("judgment") == "contradicted"
        ),
        "claims_insufficient": sum(
            1 for report in reports
            if report.get("judgment") == "insufficient_evidence"
        ),
        "verification_skipped": False,
        "reports": reports,
    }
