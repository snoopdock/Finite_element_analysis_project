#!/usr/bin/env python3
"""Bounded enrichment of extracted knowledge with scientific context."""

from __future__ import annotations

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
                full_text = evidence.get("full_text")
                if isinstance(full_text, str) and full_text.strip():
                    passages.append(full_text[:max_passage_chars])
                    continue
                excerpt = evidence.get("excerpt") or evidence.get("content")
                if isinstance(excerpt, str) and excerpt.strip():
                    passages.append(excerpt[:max_passage_chars])

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
