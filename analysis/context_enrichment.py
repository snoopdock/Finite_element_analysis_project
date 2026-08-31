#!/usr/bin/env python3
"""Bounded enrichment of extracted knowledge with scientific context."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from analysis.scientific_context import extract_context

PROPOSITION_CATEGORIES = ("rules", "equations", "procedures")


def _statement(item: Dict[str, Any], category: str) -> str:
    return str(
        item.get("rule")
        or item.get("name")
        or item.get("title")
        or item.get("description")
        or ""
    ).strip()


def _read_cached_text(evidence: Dict[str, Any], max_chars: int) -> str:
    for key in ("full_text", "content", "excerpt"):
        value = evidence.get(key)
        if isinstance(value, str) and value.strip():
            return value[:max_chars]

    path = evidence.get("full_text_path")
    if not path:
        return ""

    candidate = Path(str(path))
    candidates = [candidate]
    if not candidate.is_absolute():
        candidates.append(Path.cwd() / candidate)

    for resolved in candidates:
        if not resolved.exists() or not resolved.is_file():
            continue
        try:
            with resolved.open("r", encoding="utf-8") as handle:
                return handle.read(max_chars)
        except OSError:
            continue
    return ""


def enrich_extraction_context(
    extraction: Dict[str, Any],
    evidence_by_id: Dict[str, Dict[str, Any]],
    provider,
    parser,
    *,
    max_items: int = 3,
    max_sources_per_item: int = 2,
    max_passage_chars: int = 1800,
    model: Optional[str] = None,
    max_tokens: int = 500,
) -> Dict[str, Any]:
    """Enrich a bounded number of proposition-like items with source context."""
    result = extraction if isinstance(extraction, dict) else {}
    remaining = max(0, int(max_items))
    if remaining == 0:
        return result

    for category in PROPOSITION_CATEGORIES:
        items = result.get(category, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if remaining <= 0:
                break
            if not isinstance(item, dict):
                continue

            source_ids = item.get("source_ids", [])
            if isinstance(source_ids, str):
                source_ids = [source_ids]
            if not isinstance(source_ids, list):
                source_ids = []

            passages: List[str] = []
            for source_id in source_ids[:max(0, int(max_sources_per_item))]:
                evidence = evidence_by_id.get(str(source_id))
                if not isinstance(evidence, dict):
                    continue
                text = _read_cached_text(evidence, max_passage_chars)
                if text.strip():
                    passages.append(text)

            statement = _statement(item, category)
            if not statement or not passages:
                continue

            review = extract_context(
                statement,
                passages,
                provider,
                parser,
                model=model,
                max_tokens=max_tokens,
            )
            if review.get("skipped"):
                continue

            item["context"] = review.get("context", {})
            remaining -= 1

    return result
