#!/usr/bin/env python3
"""Deterministic citation integrity checks for generated document sections.

This module verifies citation identity and coverage. It deliberately does not
claim semantic entailment between a citation and a scientific claim; that
requires source passages and a separate semantic verification step.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Set


_CITATION_RE = re.compile(
    r"\[([A-Za-z0-9_.\-]+(?:\s*,\s*[A-Za-z0-9_.\-]+)*)\]"
)


def extract_citation_ids(text: str) -> List[str]:
    """Extract bracketed citation IDs from prose."""
    result: Set[str] = set()
    for group in _CITATION_RE.findall(str(text or "")):
        for value in group.split(","):
            value = value.strip()
            if value:
                result.add(value)
    return sorted(result)


def validate_section_citations(
    section: Dict,
    allowed_source_ids: Iterable[str],
) -> Dict:
    """Validate one section's citation IDs and report coverage."""
    allowed = {str(value) for value in allowed_source_ids if value}
    content = str(section.get("content", "")) if isinstance(section, dict) else ""
    citations = extract_citation_ids(content)
    invalid = [citation for citation in citations if citation not in allowed]

    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", content)
        if paragraph.strip()
    ]

    cited_paragraphs = sum(
        1 for paragraph in paragraphs if extract_citation_ids(paragraph)
    )

    return {
        "section_id": section.get("section_id") if isinstance(section, dict) else None,
        "citation_ids": citations,
        "invalid_citation_ids": invalid,
        "paragraphs": len(paragraphs),
        "cited_paragraphs": cited_paragraphs,
        "citation_coverage_percent": round(
            (cited_paragraphs / len(paragraphs) * 100.0)
            if paragraphs else 0.0,
            1,
        ),
        "valid": not invalid,
    }


def validate_document_citations(
    sections: List[Dict],
    evidence: List[Dict],
) -> Dict:
    """Validate citation IDs across the generated document."""
    known_sources = {
        str(item.get("source_id"))
        for item in evidence or []
        if isinstance(item, dict) and item.get("source_id")
    }

    reports = []
    invalid_sections = []
    total_paragraphs = 0
    cited_paragraphs = 0

    for section in sections or []:
        if not isinstance(section, dict):
            continue

        report = validate_section_citations(
            section,
            known_sources,
        )
        reports.append(report)
        total_paragraphs += report["paragraphs"]
        cited_paragraphs += report["cited_paragraphs"]

        if not report["valid"]:
            invalid_sections.append(
                section.get("section_id") or section.get("title", "")
            )

    return {
        "valid": not invalid_sections,
        "known_source_count": len(known_sources),
        "sections_checked": len(reports),
        "invalid_sections": invalid_sections,
        "paragraphs_checked": total_paragraphs,
        "cited_paragraphs": cited_paragraphs,
        "citation_coverage_percent": round(
            (cited_paragraphs / total_paragraphs * 100.0)
            if total_paragraphs else 0.0,
            1,
        ),
        "sections": reports,
    }
