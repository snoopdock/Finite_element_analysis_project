#!/usr/bin/env python3
"""Extract proposed validity scopes from source-backed proposition evidence."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from analysis.validity_scope import normalize_validity_scope
from analysis.validity_context_mapping import propose_validity_scope


def _full_text_from_item(item: Dict[str, Any]) -> Optional[str]:
    if not isinstance(item, dict):
        return None
    text = item.get("full_text")
    if isinstance(text, str) and text.strip():
        return text
    path = item.get("full_text_path")
    if isinstance(path, str) and path.strip():
        try:
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read()
        except OSError:
            return None
        return text if text.strip() else None
    return None


def _allowed_evidence_relation_ids(
    proposition: Dict[str, Any],
    evidence_items: List[Dict[str, Any]],
) -> set[str]:
    allowed = {
        str(value).strip()
        for value in proposition.get("evidence_relation_ids", []) or []
        if str(value).strip()
    }
    for item in evidence_items or []:
        if not isinstance(item, dict):
            continue
        for value in item.get("evidence_relation_ids", []) or []:
            text = str(value).strip()
            if text:
                allowed.add(text)
    return allowed


def extract_validity_scope(
    proposition: Dict[str, Any],
    evidence_items: List[Dict[str, Any]],
    provider,
    parser,
    *,
    model: Optional[str] = None,
    max_tokens: int = 700,
) -> Optional[Dict[str, Any]]:
    """Extract a proposed validity scope using source-backed full text.

    The model is asked only for scope information. Missing values remain unknown
    and the resulting scope is never marked assessed or verified here.
    """
    if not isinstance(proposition, dict):
        return None
    proposition_id = str(proposition.get("proposition_id") or "").strip()
    statement = str(proposition.get("statement") or proposition.get("claim") or "").strip()
    if not proposition_id or not statement or provider.budget_exhausted():
        return None

    passages = []
    for item in evidence_items or []:
        if len(passages) >= 4 or not isinstance(item, dict):
            continue
        text = _full_text_from_item(item)
        if not text:
            continue
        passages.append({
            "source_id": str(item.get("source_id", "")).strip(),
            "title": str(item.get("title", "")).strip(),
            "text": text[:5000],
        })
    if not passages:
        return None

    prompt = (
        "Extract only the validity scope claimed or supported by the supplied source text "
        "for the proposition below. Do not decide whether the proposition is true. "
        "Do not invent conditions, exceptions, frameworks, or domains. Use unknown/empty "
        "values when the sources do not support them. Return JSON only with fields: "
        "type, framework, domain_of_validity, regime, conditions, assumptions, limitations, "
        "exceptions, approximation. Do not create or guess evidence relation IDs.\n\n"
        f"PROPOSITION {proposition_id}: {statement}\n\n"
        f"SOURCES:\n{passages}"
    )

    raw = provider.generate(prompt, model=model, max_tokens=max_tokens)
    parsed = parser(raw)
    if not isinstance(parsed, dict):
        return None

    parsed["validity_id"] = str(parsed.get("validity_id") or "").strip()
    parsed["proposition_id"] = proposition_id
    parsed["status"] = "proposed"
    parsed["type"] = str(parsed.get("type") or "unknown").strip().lower()

    allowed_relations = _allowed_evidence_relation_ids(proposition, evidence_items)
    requested_relations = {
        str(value).strip()
        for value in parsed.get("evidence_relation_ids", []) or []
        if str(value).strip()
    }
    parsed["evidence_relation_ids"] = sorted(requested_relations & allowed_relations)

    if not parsed["validity_id"]:
        fallback = propose_validity_scope({"proposition_id": proposition_id, **parsed})
        if fallback:
            parsed["validity_id"] = fallback["validity_id"]

    if not parsed["validity_id"]:
        return None
    return normalize_validity_scope(parsed)
