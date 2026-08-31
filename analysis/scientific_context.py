#!/usr/bin/env python3
"""Context extraction for scientific claims and literature perspectives."""

from __future__ import annotations

import json
import re
from typing import Dict, List, Optional


SYSTEM_PROMPT = """You are a cautious scientific-context extractor.

Given a CLAIM and SOURCE PASSAGES, identify the context needed to interpret the claim.
Do not decide whether the claim is scientifically true. Extract only context stated or
strongly implied by the supplied passages.

Return ONLY valid JSON:
{
  "framework": "",
  "assumptions": [],
  "conditions": [],
  "domain_of_validity": [],
  "definitions": [],
  "parameters": [],
  "method": "",
  "approximation": [],
  "scope_notes": ""
}

Unknown fields must be empty rather than invented.
"""

_FIELDS = {
    "framework",
    "assumptions",
    "conditions",
    "domain_of_validity",
    "definitions",
    "parameters",
    "method",
    "approximation",
    "scope_notes",
}


def _clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _clean_list(value: object) -> List[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    result = []
    seen = set()
    for entry in value:
        text = _clean_text(entry)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def normalize_context(value: Optional[Dict]) -> Dict:
    """Normalize a context object without adding unsupported context."""
    value = value if isinstance(value, dict) else {}
    return {
        "framework": _clean_text(value.get("framework", "")),
        "assumptions": _clean_list(value.get("assumptions", [])),
        "conditions": _clean_list(value.get("conditions", [])),
        "domain_of_validity": _clean_list(value.get("domain_of_validity", [])),
        "definitions": _clean_list(value.get("definitions", [])),
        "parameters": _clean_list(value.get("parameters", [])),
        "method": _clean_text(value.get("method", "")),
        "approximation": _clean_list(value.get("approximation", [])),
        "scope_notes": _clean_text(value.get("scope_notes", "")),
    }


def extract_context(
    claim: str,
    passages: List[str],
    provider,
    parser,
    *,
    model: Optional[str] = None,
    max_tokens: int = 500,
) -> Dict:
    """Extract scientific context using one bounded LLM call."""
    claim = _clean_text(claim)
    passages = [_clean_text(p) for p in passages if _clean_text(p)]

    if not claim or not passages:
        return {"context": normalize_context({}), "skipped": True, "reason": "Missing claim or passages."}

    if provider.budget_exhausted():
        return {"context": normalize_context({}), "skipped": True, "reason": "LLM budget exhausted."}

    prompt = (
        "CLAIM:\n" + claim + "\n\nSOURCE PASSAGES:\n" +
        "\n\n".join(f"[{i + 1}] {p}" for i, p in enumerate(passages[:4]))
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
        return {"context": normalize_context({}), "skipped": True, "reason": error or "Empty response."}

    try:
        parsed = parser.parse(text, model_name="scientific_context")
    except Exception:
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = {}

    if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
        parsed = parsed[0]

    if not isinstance(parsed, dict):
        parsed = {}

    cleaned = {key: parsed.get(key) for key in _FIELDS}
    return {
        "context": normalize_context(cleaned),
        "skipped": False,
        "reason": "",
    }
