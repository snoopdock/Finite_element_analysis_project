#!/usr/bin/env python3
"""Stable, source-local locations for evidence used by scientific assessments."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Optional


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def evidence_location_id(
    source_id: str,
    *,
    section_type: str = "",
    page: Optional[int] = None,
    char_start: Optional[int] = None,
    char_end: Optional[int] = None,
    passage_id: str = "",
) -> str:
    """Return a stable identity for a source-local evidence location."""
    payload = "|".join(
        (
            _clean(source_id),
            _clean(section_type),
            "" if page is None else str(page),
            "" if char_start is None else str(char_start),
            "" if char_end is None else str(char_end),
            _clean(passage_id),
        )
    )
    return "loc-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def normalize_evidence_location(value: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalize source-local location metadata without inventing unavailable fields."""
    raw = value if isinstance(value, dict) else {}
    page = raw.get("page")
    try:
        page = int(page) if page is not None else None
    except (TypeError, ValueError):
        page = None

    char_start = raw.get("char_start")
    char_end = raw.get("char_end")
    try:
        char_start = int(char_start) if char_start is not None else None
    except (TypeError, ValueError):
        char_start = None
    try:
        char_end = int(char_end) if char_end is not None else None
    except (TypeError, ValueError):
        char_end = None

    return {
        "section_type": _clean(raw.get("section_type", "")),
        "section_title": _clean(raw.get("section_title", "")),
        "page": page,
        "char_start": char_start,
        "char_end": char_end,
        "passage_id": _clean(raw.get("passage_id", "")),
        "locator_text": _clean(raw.get("locator_text", "")),
    }


def make_evidence_location(source_id: str, location: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a stable, auditable source-local evidence location record."""
    source_id = _clean(source_id)
    normalized = normalize_evidence_location(location)
    return {
        "evidence_location_id": evidence_location_id(
            source_id,
            section_type=normalized["section_type"],
            page=normalized["page"],
            char_start=normalized["char_start"],
            char_end=normalized["char_end"],
            passage_id=normalized["passage_id"],
        ),
        "source_id": source_id,
        **normalized,
    }
