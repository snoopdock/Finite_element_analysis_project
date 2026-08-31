#!/usr/bin/env python3
"""Deterministic source-support checks for cited claims.

This module provides lexical/phrase overlap evidence checks. It deliberately
does not claim semantic entailment; high lexical support is only evidence that
source text overlaps with the cited claim.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Dict, Iterable, List

_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "in", "into", "is", "it", "of", "on", "or", "that", "the", "this",
    "to", "was", "were", "with", "using", "used", "use", "can", "may",
}


def _tokens(text: str) -> List[str]:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", str(text or "").lower())
    return [token for token in tokens if token not in _STOP_WORDS]


def _ngrams(tokens: List[str], size: int) -> set[tuple[str, ...]]:
    if len(tokens) < size:
        return set()
    return {tuple(tokens[i:i + size]) for i in range(len(tokens) - size + 1)}


def lexical_support_score(claim: str, source_text: str) -> float:
    """Return a bounded lexical support score in [0, 1]."""
    claim_tokens = _tokens(claim)
    source_tokens = _tokens(source_text)

    if not claim_tokens or not source_tokens:
        return 0.0

    source_counts = Counter(source_tokens)
    matched_tokens = sum(
        1
        for token in set(claim_tokens)
        if token in source_counts
    )
    token_coverage = matched_tokens / max(1, len(set(claim_tokens)))

    claim_bigrams = _ngrams(claim_tokens, 2)
    source_bigrams = _ngrams(source_tokens, 2)
    phrase_coverage = (
        len(claim_bigrams & source_bigrams) / len(claim_bigrams)
        if claim_bigrams
        else 0.0
    )

    return min(
        1.0,
        0.65 * token_coverage + 0.35 * phrase_coverage,
    )


def support_for_citations(
    claim: str,
    citation_ids: Iterable[str],
    evidence_by_id: Dict[str, Dict],
) -> Dict:
    """Score lexical support for a claim against its cited evidence."""
    ids = [str(value) for value in citation_ids if value]
    scores = {}

    for source_id in ids:
        item = evidence_by_id.get(source_id, {})
        if not isinstance(item, dict):
            scores[source_id] = 0.0
            continue

        text = str(
            item.get("full_text")
            or item.get("content")
            or item.get("abstract")
            or item.get("description")
            or ""
        )
        scores[source_id] = round(
            lexical_support_score(claim, text),
            4,
        )

    best = max(scores.values(), default=0.0)
    return {
        "supported": best > 0.20,
        "best_score": round(best, 4),
        "scores": scores,
        "method": "lexical_overlap",
    }
