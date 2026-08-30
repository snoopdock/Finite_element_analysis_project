#!/usr/bin/env python3
"""Stable identity and lineage helpers for document sections.

Section titles are presentation data and may change during OAA operations.
A section_id is therefore the stable identity used for persistent state,
history, anomaly keys, and future structural transformations.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Iterable, List, Optional

SECTION_ID_KEY = "section_id"
PARENT_SECTION_IDS_KEY = "parent_section_ids"


def new_section_id() -> str:
    """Create a new globally unique section identifier."""
    return str(uuid.uuid4())


def get_section_id(section: Any) -> Optional[str]:
    """Return a valid section UUID, or None for invalid/missing data."""
    if not isinstance(section, dict):
        return None
    value = section.get(SECTION_ID_KEY)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return str(uuid.UUID(value.strip()))
    except (ValueError, AttributeError, TypeError):
        return None


def ensure_section_id(section: Dict[str, Any]) -> str:
    """Ensure a section has a stable UUID and return it.

    Existing valid IDs are preserved. A missing or malformed ID is replaced
    with a new UUID.
    """
    existing = get_section_id(section)
    if existing is not None:
        section[SECTION_ID_KEY] = existing
        return existing

    section_id = new_section_id()
    section[SECTION_ID_KEY] = section_id
    return section_id


def normalize_parent_ids(section: Dict[str, Any]) -> List[str]:
    """Normalize and deduplicate parent section UUIDs."""
    raw = section.get(PARENT_SECTION_IDS_KEY, [])
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, Iterable):
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
    """Normalize section identities in-place and return valid section dicts.

    This function is deliberately conservative: it does not change titles,
    content, ordering, or existing valid UUIDs.
    """
    if not isinstance(sections, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        ensure_section_id(section)
        normalize_parent_ids(section)
        normalized.append(section)
    return normalized


def make_child_section(
    section: Dict[str, Any],
    *,
    title: str,
    content: str = "",
    **extra: Any,
) -> Dict[str, Any]:
    """Create a new section derived from one parent section."""
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


def make_merged_section(
    section1: Dict[str, Any],
    section2: Dict[str, Any],
    *,
    title: str,
    content: str,
    **extra: Any,
) -> Dict[str, Any]:
    """Create a new section derived from two parent sections."""
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
