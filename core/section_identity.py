#!/usr/bin/env python3
"""Stable identity and lineage helpers for document sections."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Iterable, List, Optional

SECTION_ID_KEY = "section_id"
PARENT_SECTION_IDS_KEY = "parent_section_ids"


def new_section_id() -> str:
    return str(uuid.uuid4())


def get_section_id(section: Any) -> Optional[str]:
    if not isinstance(section, dict):
        return None
    value = section.get(SECTION_ID_KEY)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return str(uuid.UUID(value.strip()))
    except (ValueError, AttributeError, TypeError):
        return None


def ensure_section_id(section: Dict[str, Any], used_ids: Optional[set] = None) -> str:
    """Ensure a section has a unique stable UUID."""
    existing = get_section_id(section)
    if existing is not None and (used_ids is None or existing not in used_ids):
        section[SECTION_ID_KEY] = existing
        if used_ids is not None:
            used_ids.add(existing)
        return existing

    section_id = new_section_id()
    while used_ids is not None and section_id in used_ids:
        section_id = new_section_id()
    section[SECTION_ID_KEY] = section_id
    if used_ids is not None:
        used_ids.add(section_id)
    return section_id


def normalize_parent_ids(section: Dict[str, Any]) -> List[str]:
    raw = section.get(PARENT_SECTION_IDS_KEY, [])
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, Iterable) or isinstance(raw, (bytes, bytearray)):
        raw = []

    result: List[str] = []
    seen = set()
    for value in raw:
        try:
            normalized = str(uuid.UUID(str(value).strip()))
        except (ValueError, AttributeError, TypeError):
            continue
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)

    section[PARENT_SECTION_IDS_KEY] = result
    return result


def normalize_sections(sections: Any) -> List[Dict[str, Any]]:
    if not isinstance(sections, list):
        return []

    normalized: List[Dict[str, Any]] = []
    used_ids = set()
    for section in sections:
        if not isinstance(section, dict):
            continue
        ensure_section_id(section, used_ids=used_ids)
        normalize_parent_ids(section)
        normalized.append(section)
    return normalized


def make_child_section(section: Dict[str, Any], *, title: str, content: str = "", **extra: Any) -> Dict[str, Any]:
    parent_id = ensure_section_id(section)
    child = {
        "section_id": new_section_id(),
        "title": title,
        "content": content,
        "parent_section_ids": [parent_id],
        "generated_from": "split",
    }
    child.update(extra)
    normalize_parent_ids(child)
    return child


def make_merged_section(section1: Dict[str, Any], section2: Dict[str, Any], *, title: str, content: str, **extra: Any) -> Dict[str, Any]:
    parent1 = ensure_section_id(section1)
    parent2 = ensure_section_id(section2)
    merged = {
        "section_id": new_section_id(),
        "title": title,
        "content": content,
        "parent_section_ids": [parent1, parent2],
        "generated_from": "merge",
    }
    merged.update(extra)
    normalize_parent_ids(merged)
    return merged
