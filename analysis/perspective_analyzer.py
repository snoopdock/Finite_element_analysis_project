#!/usr/bin/env python3
"""Context-aware comparison of scientific propositions."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Dict, List, Optional


VALID_RELATIONSHIPS = {
    "supported",
    "conditionally_supported",
    "complementary",
    "alternative",
    "different_framework",
    "appears_to_contradict",
    "contradicts_under_same_assumptions",
    "insufficient_evidence",
}

SYSTEM_PROMPT = """You are a cautious scientific perspective analyst.

Compare PROPOSITION A and PROPOSITION B using only their statements and supplied contexts.
Do not choose a winner merely because one source is more numerous, newer, or authoritative.
First consider whether differences in framework, assumptions, definitions, parameters,
conditions, domain, method, or approximation explain the apparent disagreement.

Return ONLY valid JSON:
{
  "relationship": "supported" | "conditionally_supported" | "complementary" |
                   "alternative" | "different_framework" | "appears_to_contradict" |
                   "contradicts_under_same_assumptions" | "insufficient_evidence",
  "confidence": 0.0,
  "shared_context": [],
  "different_context": [],
  "reason": "brief explanation"
}

A difference is not a contradiction merely because the conclusions differ.
Use "contradicts_under_same_assumptions" only when the available contexts materially match.
"""


def _clean(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _clean_list(value: object) -> List[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out = []
    seen = set()
    for entry in value:
        text = _clean(entry)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _comparison_id(proposition_a: Dict, proposition_b: Dict) -> str:
    ids = [
        _clean(proposition_a.get("proposition_id")),
        _clean(proposition_b.get("proposition_id")),
    ]
    payload = "|".join(sorted(ids))
    return "cmp-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def normalize_comparison(value: Optional[Dict]) -> Dict:
    value = value if isinstance(value, dict) else {}
    relationship = _clean(value.get("relationship", "insufficient_evidence")).lower()
    if relationship not in VALID_RELATIONSHIPS:
        relationship = "insufficient_evidence"
    try:
        confidence = max(0.0, min(1.0, float(value.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "relationship": relationship,
        "confidence": round(confidence, 4),
        "shared_context": _clean_list(value.get("shared_context", [])),
        "different_context": _clean_list(value.get("different_context", [])),
        "reason": _clean(value.get("reason", "")),
    }


def compare_propositions(
    proposition_a: Dict,
    proposition_b: Dict,
    provider,
    parser,
    *,
    model: Optional[str] = None,
    max_tokens: int = 600,
) -> Dict:
    """Compare two propositions with one bounded LLM call."""
    comparison_id = _comparison_id(proposition_a, proposition_b)
    if provider.budget_exhausted():
        return {
            "comparison_id": comparison_id,
            "proposition_ids": [
                proposition_a.get("proposition_id"),
                proposition_b.get("proposition_id"),
            ],
            "comparison": normalize_comparison({}),
            "skipped": True,
            "reason": "LLM budget exhausted.",
        }

    prompt = (
        "PROPOSITION A:\n" + _clean(proposition_a.get("statement", "")) +
        "\nCONTEXT A:\n" + json.dumps(proposition_a.get("context", {}), ensure_ascii=False) +
        "\n\nPROPOSITION B:\n" + _clean(proposition_b.get("statement", "")) +
        "\nCONTEXT B:\n" + json.dumps(proposition_b.get("context", {}), ensure_ascii=False)
    )

    text, error = provider.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=max_tokens,
        model=model,
    )

    if error or not text:
        return {
            "comparison_id": comparison_id,
            "proposition_ids": [
                proposition_a.get("proposition_id"),
                proposition_b.get("proposition_id"),
            ],
            "comparison": normalize_comparison({}),
            "skipped": True,
            "reason": error or "Empty response.",
        }

    try:
        parsed = parser.parse(text, model_name="perspective_analyzer")
    except Exception:
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = {}

    if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
        parsed = parsed[0]

    comparison = normalize_comparison(parsed)
    return {
        "comparison_id": comparison_id,
        "proposition_ids": [
            proposition_a.get("proposition_id"),
            proposition_b.get("proposition_id"),
        ],
        "source_ids": sorted({
            str(value)
            for value in list(proposition_a.get("source_ids", [])) + list(proposition_b.get("source_ids", []))
            if value
        }),
        "comparison": comparison,
        "skipped": False,
        "reason": "",
    }
