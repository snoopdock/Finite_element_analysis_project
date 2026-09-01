#!/usr/bin/env python3
"""Conservative proposition-level relevance assessment for source evidence."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional


VALID_RELATIONS = {
    "supports",
    "challenges",
    "qualifies",
    "provides_context_for",
    "does_not_address",
    "unknown",
}

_SYSTEM_PROMPT = """You are a cautious scientific evidence-relevance analyst.

Given a PROPOSITION and SOURCE PASSAGES, determine what evidential role the passages have
with respect to the proposition. Judge only what is supported by the supplied passages.
Do not infer that a source supports a proposition merely because both concern the same topic.
Distinguish direct support from qualification, challenge, and contextual discussion.
If the passages do not address the proposition, return does_not_address.
If the evidence is too ambiguous to classify, return unknown.

Return ONLY valid JSON:
{
  "relationship": "supports|challenges|qualifies|provides_context_for|does_not_address|unknown",
  "confidence": 0.0,
  "reason": "brief evidence-based explanation",
  "passage_indices": []
}
"""


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _clean_indices(value: Any, size: int) -> List[int]:
    if isinstance(value, int):
        value = [value]
    if not isinstance(value, list):
        return []
    result: List[int] = []
    seen = set()
    for raw in value:
        try:
            index = int(raw)
        except (TypeError, ValueError):
            continue
        if 1 <= index <= size and index not in seen:
            seen.add(index)
            result.append(index)
    return result


def normalize_evidence_relevance(value: Optional[Dict[str, Any]], passage_count: int = 0) -> Dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    relationship = _clean(raw.get("relationship", "unknown")).lower()
    if relationship not in VALID_RELATIONS:
        relationship = "unknown"
    try:
        confidence = max(0.0, min(1.0, float(raw.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "relationship": relationship,
        "confidence": round(confidence, 4),
        "reason": _clean(raw.get("reason", "")),
        "passage_indices": _clean_indices(raw.get("passage_indices", []), passage_count),
    }


def assess_evidence_relevance(
    proposition: Dict[str, Any],
    passages: List[str],
    provider,
    parser,
    *,
    model: Optional[str] = None,
    max_tokens: int = 500,
) -> Dict[str, Any]:
    """Assess proposition-level evidence relevance using one bounded LLM call."""
    proposition_id = _clean(proposition.get("proposition_id")) if isinstance(proposition, dict) else ""
    clean_passages = [_clean(passage) for passage in passages or [] if _clean(passage)]

    provenance = {
        "proposition_id": proposition_id,
        "source_ids": sorted({
            str(value).strip()
            for value in (proposition.get("source_ids", []) if isinstance(proposition, dict) else []) or []
            if str(value).strip()
        }),
    }

    if not proposition_id or not _clean(proposition.get("statement")):
        return {**provenance, "relevance": normalize_evidence_relevance({}, 0), "skipped": True, "reason": "Missing proposition identity or statement."}
    if not clean_passages:
        return {**provenance, "relevance": normalize_evidence_relevance({}, 0), "skipped": True, "reason": "Missing source passages."}
    if provider.budget_exhausted():
        return {**provenance, "relevance": normalize_evidence_relevance({}, len(clean_passages)), "skipped": True, "reason": "LLM budget exhausted."}

    context = proposition.get("context", {})
    if not isinstance(context, dict):
        context = {}
    prompt = (
        "PROPOSITION:\n" + _clean(proposition.get("statement")) +
        "\n\nPROPOSITION CONTEXT:\n" + json.dumps(context, ensure_ascii=False) +
        "\n\nSOURCE PASSAGES:\n" +
        "\n\n".join(f"[{index + 1}] {passage}" for index, passage in enumerate(clean_passages[:8]))
    )

    text, error = provider.chat(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=max_tokens,
        model=model,
    )
    if error or not text:
        return {**provenance, "relevance": normalize_evidence_relevance({}, len(clean_passages)), "skipped": True, "reason": error or "Empty response."}

    try:
        parsed = parser.parse(text, model_name="evidence_relevance")
    except Exception:
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = {}
    if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
        parsed = parsed[0]
    relevance = normalize_evidence_relevance(parsed if isinstance(parsed, dict) else {}, len(clean_passages))

    return {
        **provenance,
        "relevance": relevance,
        "skipped": False,
        "reason": "",
    }
