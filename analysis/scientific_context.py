#!/usr/bin/env python3
"""Context extraction for scientific claims and literature perspectives."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional


SYSTEM_PROMPT = """You are a cautious scientific-context extractor.

Given a CLAIM and SOURCE PASSAGES, identify the context needed to interpret the claim.
Do not decide whether the claim is scientifically true. Extract only context stated or
strongly implied by the supplied passages.

Return ONLY valid JSON:
{
  "framework": "",
  "assumptions": [],
  "definitions": [],
  "conditions": [],
  "domain_of_validity": [],
  "parameters": {},
  "boundary_conditions": [],
  "initial_conditions": [],
  "method": "",
  "approximation": [],
  "scope": ""
}

Unknown fields must be empty rather than invented.
"""

TEXT_FIELDS = {"framework", "method", "scope"}
LIST_FIELDS = {
    "assumptions",
    "definitions",
    "conditions",
    "domain_of_validity",
    "boundary_conditions",
    "initial_conditions",
    "approximation",
}
PARAMETER_FIELD = "parameters"


def _clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _clean_list(value: object) -> List[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    result: List[str] = []
    seen = set()
    for entry in value:
        text = _clean_text(entry)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _clean_parameters(value: object) -> Dict[str, str]:
    if not isinstance(value, dict):
        return {}
    result: Dict[str, str] = {}
    for key, raw_value in value.items():
        clean_key = _clean_text(key)
        clean_value = _clean_text(raw_value)
        if clean_key and clean_value:
            result[clean_key] = clean_value
    return result


def normalize_context(value: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalize context without inventing unsupported scientific information."""
    raw = value if isinstance(value, dict) else {}
    result: Dict[str, Any] = {}
    for field in TEXT_FIELDS:
        result[field] = _clean_text(raw.get(field, ""))
    for field in LIST_FIELDS:
        result[field] = _clean_list(raw.get(field, []))
    result[PARAMETER_FIELD] = _clean_parameters(raw.get(PARAMETER_FIELD, {}))
    result["scope_notes"] = result["scope"]
    return result


def context_difference(
    context_a: Optional[Dict[str, Any]],
    context_b: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return field-level context differences; not a contradiction judgment."""
    a = normalize_context(context_a)
    b = normalize_context(context_b)
    differences: Dict[str, Any] = {}
    for field in (*sorted(TEXT_FIELDS), *sorted(LIST_FIELDS), PARAMETER_FIELD):
        if a[field] != b[field]:
            differences[field] = {"a": a[field], "b": b[field]}
    return differences


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

    prompt = "CLAIM:\n" + claim + "\n\nSOURCE PASSAGES:\n" + "\n\n".join(
        f"[{i + 1}] {p}" for i, p in enumerate(passages[:4])
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
    if "scope" not in parsed and "scope_notes" in parsed:
        parsed["scope"] = parsed["scope_notes"]
    if not isinstance(parsed.get("parameters", {}), dict):
        parsed["parameters"] = {}

    return {"context": normalize_context(parsed), "skipped": False, "reason": ""}
