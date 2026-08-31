#!/usr/bin/env python3
"""Deterministic candidate selection for scientific perspective comparison."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


def _tokens(text: object) -> set[str]:
    return set(re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", str(text or "").lower()))


def _overlap(left: Dict[str, Any], right: Dict[str, Any]) -> float:
    a = _tokens(left.get("statement", ""))
    b = _tokens(right.get("statement", ""))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def candidate_pairs(
    propositions: List[Dict[str, Any]],
    *,
    max_pairs: int = 8,
    minimum_overlap: float = 0.15,
) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """Select deterministic, bounded proposition pairs likely to discuss the same subject."""
    candidates = []
    records = [item for item in propositions or [] if isinstance(item, dict) and item.get("proposition_id")]
    records.sort(key=lambda item: str(item.get("proposition_id")))

    for index, left in enumerate(records):
        left_sources = set(str(value) for value in left.get("source_ids", []) if value)
        for right in records[index + 1:]:
            right_sources = set(str(value) for value in right.get("source_ids", []) if value)
            if left_sources and right_sources and left_sources.intersection(right_sources):
                continue
            score = _overlap(left, right)
            if score < float(minimum_overlap):
                continue
            candidates.append((score, str(left.get("proposition_id")), str(right.get("proposition_id")), left, right))

    candidates.sort(key=lambda row: (-row[0], row[1], row[2]))
    return [(row[3], row[4]) for row in candidates[: max(0, int(max_pairs))]]
