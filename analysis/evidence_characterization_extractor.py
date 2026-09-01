#!/usr/bin/env python3
"""Bounded source-backed extraction of scientific evidence characterization."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from analysis.evidence_characterization import normalize_evidence_characterization


SYSTEM_PROMPT = """You are a cautious scientific-evidence characterization extractor.

Given a SOURCE record and SOURCE PASSAGES from its full text, characterize the role and
nature of the evidence. Do not infer peer-review, replication, or publication status from
the writing style. Do not infer facts that are not supported by the supplied source record
or passages. Unknown values must be returned as 'unknown' or empty lists.

Return ONLY valid JSON:
{
  "study_type": "theoretical|experimental|observational|simulation|computational|review|survey|methodological|mixed|unknown",
  "evidence_role": "primary|secondary|background|methodological|replication|critique|review|unknown",
  "primary_or_secondary": "primary|secondary|mixed|unknown",
  "methodological_description": "",
  "limitations": [],
  "notes": []
}
"""


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _clean_passages(passages: List[str]) -> List[str]:
    result: List[str] = []
    for passage in passages or []:
        text = _clean(passage)
        if text:
            result.append(text)
    return result


def extract_evidence_characterization(
    source: Dict[str, Any],
    passages: List[str],
    provider,
    parser,
    *,
    model: Optional[str] = None,
    max_tokens: int = 450,
) -> Dict[str, Any]:
    """Extract characterization from full-text passages with conservative defaults."""
    source = source if isinstance(source, dict) else {}
    passages = _clean_passages(passages)
    source_id = _clean(source.get("source_id"))

    if not source_id or not passages:
        return {
            "source_id": source_id,
            "characterization": normalize_evidence_characterization({}),
            "skipped": True,
            "reason": "Missing source identity or full-text passages.",
        }
    if provider.budget_exhausted():
        return {
            "source_id": source_id,
            "characterization": normalize_evidence_characterization({}),
            "skipped": True,
            "reason": "LLM budget exhausted.",
        }

    source_context = {
        "source_id": source_id,
        "title": _clean(source.get("title")),
        "source_type": _clean(source.get("source_type")),
        "publication_status": _clean(source.get("publication_status")),
    }
    prompt = (
        "SOURCE RECORD:\n" + json.dumps(source_context, ensure_ascii=False) +
        "\n\nSOURCE PASSAGES:\n" +
        "\n\n".join(f"[{index + 1}] {passage}" for index, passage in enumerate(passages[:6]))
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
            "source_id": source_id,
            "characterization": normalize_evidence_characterization({}),
            "skipped": True,
            "reason": error or "Empty response.",
        }

    try:
        parsed = parser.parse(text, model_name="evidence_characterization")
    except Exception:
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = {}
    if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
        parsed = parsed[0]
    if not isinstance(parsed, dict):
        parsed = {}

    # Publication status and replication are intentionally never guessed here.
    characterization = normalize_evidence_characterization({
        **parsed,
        "publication_status": source.get("publication_status", "unknown"),
        "replication_status": source.get("replication_status", "unknown"),
    })

    return {
        "source_id": source_id,
        "characterization": characterization,
        "skipped": False,
        "reason": "",
    }
