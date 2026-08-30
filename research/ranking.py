#!/usr/bin/env python3
"""Deterministic evidence ranking utilities.

Ranking is intentionally independent from retrieval so that source selection
can be inspected, tuned, and tested without changing the providers.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, Iterable, List, Sequence, Set


DEFAULT_STOP_WORDS: Set[str] = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for",
    "from", "in", "into", "is", "it", "of", "on", "or", "that",
    "the", "this", "to", "was", "were", "with", "method", "finite",
    "element", "elements", "using", "used", "use", "can", "may",
}


SOURCE_QUALITY = {
    "peer_reviewed": 1.00,
    "journal": 1.00,
    "conference": 0.95,
    "book": 0.95,
    "preprint": 0.85,
    "arxiv": 0.85,
    "academic": 0.85,
    "reference": 0.65,
    "encyclopedia": 0.60,
    "wikipedia": 0.55,
    "web": 0.40,
    "unknown": 0.30,
}


def tokenize(text: str) -> List[str]:
    """Normalize technical prose into lowercase word tokens."""
    if not isinstance(text, str):
        text = str(text or "")
    return [
        token
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", text.lower())
        if token not in DEFAULT_STOP_WORDS
    ]


def lexical_score(query: str, text: str) -> float:
    """Compute a bounded weighted lexical relevance score.

    Title/name matches receive more weight than generic body matches.
    """
    query_tokens = set(tokenize(query))
    text_tokens = tokenize(text)

    if not query_tokens or not text_tokens:
        return 0.0

    frequencies = Counter(text_tokens)
    matched = query_tokens.intersection(frequencies)
    if not matched:
        return 0.0

    score = 0.0
    for token in matched:
        # Diminishing returns for repeated words.
        score += 1.0 + math.log1p(frequencies[token])

    return min(1.0, score / (2.5 * len(query_tokens)))


def source_quality_score(item: Dict) -> float:
    """Return an evidence-quality prior from explicit source metadata."""
    source_type = str(
        item.get("source_type")
        or item.get("provider")
        or item.get("source")
        or "unknown"
    ).lower()

    if "wikipedia" in source_type:
        return SOURCE_QUALITY["wikipedia"]
    if "arxiv" in source_type:
        return SOURCE_QUALITY["arxiv"]
    if "semantic" in source_type:
        return SOURCE_QUALITY["academic"]
    if "journal" in source_type:
        return SOURCE_QUALITY["journal"]
    if "book" in source_type:
        return SOURCE_QUALITY["book"]

    return SOURCE_QUALITY.get(source_type, SOURCE_QUALITY["unknown"])


def section_relevance_score(
    topic: str,
    section_type: str,
    text: str,
) -> float:
    """Prefer article sections whose type/content is relevant to the topic."""
    if not section_type:
        return lexical_score(topic, text)

    section_tokens = set(tokenize(section_type))
    topic_tokens = set(tokenize(topic))
    overlap = len(section_tokens.intersection(topic_tokens))
    structural = overlap / max(1, len(topic_tokens))
    return max(structural, lexical_score(topic, text) * 0.5)


def rank_items(
    query: str,
    items: Sequence[Dict],
    *,
    top_k: int = 4,
    lexical_weight: float = 0.50,
    source_weight: float = 0.20,
    section_weight: float = 0.10,
    citation_weight: float = 0.20,
) -> List[Dict]:
    """Rank evidence or knowledge-base items and annotate their scores."""
    if not isinstance(items, Sequence):
        return []

    prepared = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue

        title = str(item.get("title") or item.get("name") or "")
        body = str(
            item.get("content")
            or item.get("abstract")
            or item.get("explanation")
            or item.get("description")
            or ""
        )
        combined = f"{title}\n{body}"

        lex = lexical_score(query, f"{title} {title} {body}")
        quality = source_quality_score(item)
        section = section_relevance_score(
            query,
            str(item.get("section_type") or ""),
            combined,
        )

        citations = item.get("source_ids", [])
        citation_support = 1.0 if citations else 0.0

        score = (
            lexical_weight * lex
            + source_weight * quality
            + section_weight * section
            + citation_weight * citation_support
        )

        annotated = dict(item)
        annotated["ranking"] = {
            "score": round(score, 6),
            "lexical": round(lex, 6),
            "source_quality": round(quality, 6),
            "section_relevance": round(section, 6),
            "citation_support": round(citation_support, 6),
        }
        prepared.append((score, index, annotated))

    prepared.sort(key=lambda row: (-row[0], row[1]))
    return [row[2] for row in prepared[:max(0, int(top_k))]]


def rank_knowledge_items(
    topic: str,
    knowledge_base: Dict,
    *,
    top_k: int = 6,
) -> List[Dict]:
    """Rank heterogeneous knowledge-base records for a writing topic."""
    items = []
    if not isinstance(knowledge_base, dict):
        return []

    for category in ("concepts", "equations", "procedures", "rules"):
        records = knowledge_base.get(category, [])
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            item = dict(record)
            item["item_type"] = category[:-1] if category.endswith("s") else category
            items.append(item)

    return rank_items(
        topic,
        items,
        top_k=top_k,
        lexical_weight=0.70,
        source_weight=0.15,
        section_weight=0.05,
        citation_weight=0.10,
    )
