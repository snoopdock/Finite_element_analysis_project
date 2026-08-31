#!/usr/bin/env python3
"""Deterministic evidence ranking utilities."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Sequence, Set

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
    if not isinstance(text, str):
        text = str(text or "")
    return [
        token
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", text.lower())
        if token not in DEFAULT_STOP_WORDS
    ]


def lexical_score(query: str, text: str) -> float:
    query_tokens = set(tokenize(query))
    text_tokens = tokenize(text)
    if not query_tokens or not text_tokens:
        return 0.0

    frequencies = Counter(text_tokens)
    matched = query_tokens.intersection(frequencies)
    if not matched:
        return 0.0

    score = sum(1.0 + math.log1p(frequencies[token]) for token in matched)
    return min(1.0, score / (2.5 * len(query_tokens)))


def _quality_for_value(value: object) -> float:
    text = str(value or "unknown").lower()
    if "wikipedia" in text:
        return SOURCE_QUALITY["wikipedia"]
    if "arxiv" in text:
        return SOURCE_QUALITY["arxiv"]
    if "semantic" in text:
        return SOURCE_QUALITY["academic"]
    if "peer_reviewed" in text:
        return SOURCE_QUALITY["peer_reviewed"]
    if "journal" in text:
        return SOURCE_QUALITY["journal"]
    if "conference" in text:
        return SOURCE_QUALITY["conference"]
    if "book" in text:
        return SOURCE_QUALITY["book"]
    return SOURCE_QUALITY.get(text, SOURCE_QUALITY["unknown"])


def source_quality_score(item: Dict) -> float:
    """Return the strongest quality prior represented by known provenance."""
    values = []

    for key in ("source_type", "provider", "source"):
        value = item.get(key)
        if value:
            values.append(_quality_for_value(value))

    for key in ("source_types", "provider_names"):
        value = item.get(key, [])
        if isinstance(value, str):
            value = [value]
        if isinstance(value, list):
            values.extend(_quality_for_value(entry) for entry in value if entry)

    return max(values, default=SOURCE_QUALITY["unknown"])


def section_relevance_score(topic: str, section_type: str, text: str) -> float:
    if not section_type:
        return lexical_score(topic, text)
    section_tokens = set(tokenize(section_type))
    topic_tokens = set(tokenize(topic))
    overlap = len(section_tokens.intersection(topic_tokens))
    structural = overlap / max(1, len(topic_tokens))
    return max(structural, lexical_score(topic, text) * 0.5)


def _normalize_weights(
    lexical_weight: float,
    source_weight: float,
    section_weight: float,
    citation_weight: float,
) -> tuple[float, float, float, float]:
    weights = [
        float(lexical_weight),
        float(source_weight),
        float(section_weight),
        float(citation_weight),
    ]

    if any(weight < 0.0 or not math.isfinite(weight) for weight in weights):
        raise ValueError("Ranking weights must be finite and non-negative.")

    total = sum(weights)
    if total <= 0.0:
        raise ValueError("Ranking weights must contain at least one positive value.")

    return tuple(weight / total for weight in weights)


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
    """Rank items for one query and annotate component scores."""
    if not isinstance(items, Sequence):
        return []

    (
        lexical_weight,
        source_weight,
        section_weight,
        citation_weight,
    ) = _normalize_weights(
        lexical_weight,
        source_weight,
        section_weight,
        citation_weight,
    )

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
        citation_support = 1.0 if item.get("source_ids") else 0.0

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
            "weights": {
                "lexical": round(lexical_weight, 6),
                "source_quality": round(source_weight, 6),
                "section_relevance": round(section_weight, 6),
                "citation_support": round(citation_weight, 6),
            },
        }
        prepared.append((score, index, annotated))

    prepared.sort(key=lambda row: (-row[0], row[1]))
    return [row[2] for row in prepared[:max(0, int(top_k))]]


def rank_items_for_queries(
    queries: Sequence[str],
    items: Sequence[Dict],
    *,
    top_k: int = 4,
) -> List[Dict]:
    """Score each item against all queries and retain best score/provenance."""
    if not queries or not items:
        return []

    best: Dict[str, Dict] = {}

    for query_index, query in enumerate(queries):
        normalized_query = str(query).strip()
        if not normalized_query:
            continue

        ranked = rank_items(
            normalized_query,
            items,
            top_k=len(items),
            lexical_weight=0.65,
            source_weight=0.25,
            section_weight=0.10,
            citation_weight=0.0,
        )

        for item in ranked:
            source_id = str(
                item.get("source_id")
                or f"__item_{query_index}_{len(best)}"
            )
            ranking = dict(item.get("ranking", {}))
            score = float(ranking.get("score", 0.0))

            current = best.get(source_id)
            if current is None:
                annotated = dict(item)
                annotated["ranking"] = dict(ranking)
                annotated["ranking"]["best_query"] = normalized_query
                annotated["ranking"]["query_index"] = query_index
                annotated["ranking"]["per_query_scores"] = {
                    normalized_query: score,
                }
                best[source_id] = annotated
                continue

            current_ranking = dict(current.get("ranking", {}))
            per_query_scores = dict(
                current_ranking.get("per_query_scores", {})
            )
            per_query_scores[normalized_query] = score
            current_ranking["per_query_scores"] = per_query_scores

            current_score = float(current_ranking.get("score", 0.0))
            current_query = str(current_ranking.get("best_query", ""))
            better = score > current_score
            if score == current_score and normalized_query < current_query:
                better = True

            if better:
                for key in (
                    "score",
                    "lexical",
                    "source_quality",
                    "section_relevance",
                    "citation_support",
                    "weights",
                ):
                    if key in ranking:
                        current_ranking[key] = ranking[key]
                current_ranking["best_query"] = normalized_query
                current_ranking["query_index"] = query_index

            current["ranking"] = current_ranking

            for key in ("query_contexts", "provider_names", "source_types"):
                incoming = item.get(key, [])
                existing = current.get(key, [])
                if not isinstance(incoming, list):
                    incoming = [incoming] if incoming else []
                if not isinstance(existing, list):
                    existing = [existing] if existing else []
                current[key] = sorted({str(value) for value in existing + incoming if value})

    result = list(best.values())
    result.sort(
        key=lambda item: (
            -float(item.get("ranking", {}).get("score", 0.0)),
            str(item.get("source_id", "")),
        )
    )
    return result[:max(0, int(top_k))]


def rank_knowledge_items(
    topic: str,
    knowledge_base: Dict,
    *,
    top_k: int = 6,
) -> List[Dict]:
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
            item["item_type"] = (
                category[:-1]
                if category.endswith("s")
                else category
            )
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
