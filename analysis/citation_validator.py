#!/usr/bin/env python3
"""Deterministic citation integrity checks for generated document sections.

This module verifies citation identity and coverage. It also reports a
lexical-overlap support signal against cited source text when that text is
available locally. It deliberately does not claim semantic entailment.
"""

from __future__ import annotations

import os
import pathlib
import re
from typing import Dict, Iterable, List, Set

from analysis.evidence_support import support_for_citations


ROOT = pathlib.Path(__file__).resolve().parents[1]

_CITATION_RE = re.compile(
    r"\[([^\[\]\s,]+(?:\s*,\s*[^\[\]\s,]+)*)\]"
)


def extract_citation_ids(text: str) -> List[str]:
    """Extract comma-separated bracketed citation IDs from prose."""
    result: Set[str] = set()
    for group in _CITATION_RE.findall(str(text or "")):
        for value in group.split(","):
            value = value.strip()
            if value:
                result.add(value)
    return sorted(result)


def _source_text(item: Dict) -> str:
    """Return available source text without downloading new material."""
    for key in ("full_text", "content", "abstract", "description"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value

    path = item.get("full_text_path")
    if not path or not isinstance(path, str):
        return ""

    candidate = pathlib.Path(path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate

    if not candidate.exists():
        return ""

    try:
        with open(candidate, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def validate_section_citations(
    section: Dict,
    allowed_source_ids: Iterable[str],
    evidence_by_id: Dict[str, Dict] | None = None,
) -> Dict:
    """Validate one section's citation IDs and report coverage/support."""
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

    evidence_by_id = evidence_by_id or {}
    support_reports = []
    supported_paragraphs = 0

    for paragraph in paragraphs:
        paragraph_citations = extract_citation_ids(paragraph)
        if not paragraph_citations:
            continue

        report = support_for_citations(
            paragraph,
            [citation for citation in paragraph_citations if citation in allowed],
            evidence_by_id,
        )
        support_reports.append(report)
        if report["supported"]:
            supported_paragraphs += 1

    return {
        "section_id": section.get("section_id") if isinstance(section, dict) else None,
        "citation_ids": citations,
        "invalid_citation_ids": invalid,
        "paragraphs": len(paragraphs),
        "cited_paragraphs": cited_paragraphs,
        "lexically_supported_paragraphs": supported_paragraphs,
        "lexical_support_coverage_percent": round(
            (supported_paragraphs / cited_paragraphs * 100.0)
            if cited_paragraphs else 0.0,
            1,
        ),
        "support_method": "lexical_overlap",
        "support_reports": support_reports,
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
    """Validate citation IDs and report lexical source-support signals."""
    known_sources = {
        str(item.get("source_id"))
        for item in evidence or []
        if isinstance(item, dict) and item.get("source_id")
    }

    evidence_by_id = {
        str(item.get("source_id")): dict(item)
        for item in evidence or []
        if isinstance(item, dict) and item.get("source_id")
    }

    for item in evidence_by_id.values():
        item["full_text"] = _source_text(item)

    reports = []
    invalid_sections = []
    total_paragraphs = 0
    cited_paragraphs = 0
    supported_paragraphs = 0

    for section in sections or []:
        if not isinstance(section, dict):
            continue

        report = validate_section_citations(
            section,
            known_sources,
            evidence_by_id=evidence_by_id,
        )
        reports.append(report)
        total_paragraphs += report["paragraphs"]
        cited_paragraphs += report["cited_paragraphs"]
        supported_paragraphs += report["lexically_supported_paragraphs"]

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
        "lexically_supported_paragraphs": supported_paragraphs,
        "citation_coverage_percent": round(
            (cited_paragraphs / total_paragraphs * 100.0)
            if total_paragraphs else 0.0,
            1,
        ),
        "lexical_support_coverage_percent": round(
            (supported_paragraphs / cited_paragraphs * 100.0)
            if cited_paragraphs else 0.0,
            1,
        ),
        "support_method": "lexical_overlap",
        "sections": reports,
    }
