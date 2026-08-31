#!/usr/bin/env python3
"""Bounded corrective rewriting for semantically contradicted claims."""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from writing.output_validator import WritingValidationError, validate_paragraph


SYSTEM_PROMPT = """You are a careful academic technical editor.

Rewrite only the supplied paragraph so that it is consistent with the supplied
source passages. Use only information supported by those passages.
Do not add unsupported facts. Preserve useful equations when supported.
Keep the citation IDs that are supported by the passages and remove any
citation that is no longer justified.
Return only the rewritten paragraph text; no markdown, JSON, title, or commentary.
"""


def _source_passages(job: Dict) -> List[str]:
    passages: List[str] = []
    for source in job.get("source_reports", []):
        if not isinstance(source, dict):
            continue
        for passage in source.get("passages", []):
            if isinstance(passage, str) and passage.strip() and passage.strip() not in passages:
                passages.append(passage.strip())
    return passages


def rewrite_paragraph(job: Dict, provider, *, model: Optional[str] = None, max_tokens: int = 900) -> Dict:
    """Rewrite one paragraph from cited source passages using one bounded LLM call."""
    paragraph = str(job.get("claim", "")).strip()
    passages = _source_passages(job)

    if not paragraph or not passages:
        return {
            "success": False,
            "text": paragraph,
            "error": "No paragraph or source passages available.",
        }

    if provider.budget_exhausted():
        return {
            "success": False,
            "text": paragraph,
            "error": "LLM rewrite budget exhausted.",
        }

    prompt = (
        "ORIGINAL PARAGRAPH:\n"
        + paragraph
        + "\n\nSOURCE PASSAGES:\n"
        + "\n\n".join(
            f"[{index + 1}] {passage}"
            for index, passage in enumerate(passages[:4])
        )
        + "\n\nREASON FOR CORRECTION:\n"
        + str(job.get("reason", ""))
    )

    text, error = provider.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=max_tokens,
        model=model,
    )

    if error or not text:
        return {
            "success": False,
            "text": paragraph,
            "error": error or "Empty rewrite response.",
        }

    text = re.sub(r"\s+", " ", str(text)).strip()

    try:
        validated = validate_paragraph(text, min_words=20)
    except WritingValidationError as exc:
        return {
            "success": False,
            "text": paragraph,
            "error": str(exc),
        }

    return {
        "success": True,
        "text": validated["text"],
        "error": None,
    }
