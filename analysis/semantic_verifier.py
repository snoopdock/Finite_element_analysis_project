#!/usr/bin/env python3
"""Passage-aware semantic verification of generated claims.

The verifier compares a generated claim with passages from cited full text and
asks the configured LLM for a three-way judgment. It deliberately requires
actual source passages and never treats citation identity or lexical overlap
as semantic proof.
"""

from __future__ import annotations

import json
import re
from typing import Dict, Iterable, List, Optional

from analysis.evidence_support import lexical_support_score


SYSTEM_PROMPT = """You are a cautious scientific evidence verifier.

Determine whether the CLAIM is supported by the supplied SOURCE PASSAGES.
Use only the supplied passages. Do not rely on outside knowledge.

Return ONLY valid JSON with exactly this structure:
{
  "judgment": "supported" | "contradicted" | "insufficient_evidence",
  "confidence": 0.0,
  "reason": "brief explanation grounded in the passages"
}

Rules:
- "supported" means the passages materially support the claim.
- "contradicted" means the passages materially conflict with the claim.
- "insufficient_evidence" means the passages do not establish the claim.
- Do not infer missing premises.
- Confidence must be a number from 0.0 to 1.0.
"""

_VALID_JUDGMENTS = {
    "supported",
    "contradicted",
    "insufficient_evidence",
}


def _normalize_text(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _source_text(item: Dict) -> str:
    for key in ("full_text", "content"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value

    path = item.get("full_text_path")
    if not isinstance(path, str) or not path:
        return ""

    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def select_source_passages(
    claim: str,
    source_text: str,
    *,
    max_passages: int = 3,
    passage_chars: int = 1800,
) -> List[str]:
    """Select lexical-nearest source passages for semantic verification."""
    text = _normalize_text(source_text)
    claim = _normalize_text(claim)
    if not text or not claim:
        return []

    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if sentence.strip()
    ]

    candidates = []
    for index, _ in enumerate(sentences):
        start = max(0, index - 1)
        end = min(len(sentences), index + 2)
        passage = " ".join(sentences[start:end])
        passage = passage[:passage_chars].strip()
        score = lexical_support_score(claim, passage)
        candidates.append((score, index, passage))

    candidates.sort(key=lambda row: (-row[0], row[1]))
    selected = []
    seen = set()

    for _, _, passage in candidates:
        if passage in seen:
            continue
        seen.add(passage)
        selected.append(passage)
        if len(selected) >= max(0, int(max_passages)):
            break

    return selected


def _parse_verifier_response(parser, text: str) -> Optional[Dict]:
    if not text or not isinstance(text, str):
        return None

    try:
        result = parser.parse(text, model_name="semantic_verifier")
    except Exception:
        try:
            result = json.loads(text)
        except Exception:
            return None

    if isinstance(result, list) and len(result) == 1 and isinstance(result[0], dict):
        result = result[0]

    if not isinstance(result, dict):
        return None

    judgment = str(result.get("judgment", "")).strip().lower()
    if judgment not in _VALID_JUDGMENTS:
        return None

    try:
        confidence = float(result.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    confidence = max(0.0, min(1.0, confidence))
    reason = _normalize_text(result.get("reason", ""))

    return {
        "judgment": judgment,
        "confidence": round(confidence, 4),
        "reason": reason,
    }


def verify_claim(
    claim: str,
    citation_ids: Iterable[str],
    evidence_by_id: Dict[str, Dict],
    provider,
    parser,
    *,
    max_sources: int = 2,
    max_passages_per_source: int = 2,
    max_passage_chars: int = 1800,
    model: Optional[str] = None,
    max_tokens: int = 700,
) -> Dict:
    """Verify a claim against cited full-text passages using LLM calls."""
    claim = _normalize_text(claim)
    source_reports = []
    source_verdicts = []

    for source_id in [str(value) for value in citation_ids if value][:max_sources]:
        item = evidence_by_id.get(source_id, {})
        if not isinstance(item, dict):
            continue

        source_text = _source_text(item)
        if not source_text:
            source_reports.append({
                "source_id": source_id,
                "judgment": "insufficient_evidence",
                "confidence": 1.0,
                "reason": "No full text is available for this cited source.",
                "passages": [],
            })
            source_verdicts.append("insufficient_evidence")
            continue

        passages = select_source_passages(
            claim,
            source_text,
            max_passages=max_passages_per_source,
            passage_chars=max_passage_chars,
        )

        if not passages:
            source_reports.append({
                "source_id": source_id,
                "judgment": "insufficient_evidence",
                "confidence": 1.0,
                "reason": "No relevant source passage could be selected.",
                "passages": [],
            })
            source_verdicts.append("insufficient_evidence")
            continue

        user_prompt = (
            "CLAIM:\n"
            + claim
            + "\n\nSOURCE PASSAGES:\n"
            + "\n\n".join(
                f"[{index + 1}] {passage}"
                for index, passage in enumerate(passages)
            )
        )

        if provider.budget_exhausted():
            return {
                "judgment": "insufficient_evidence",
                "confidence": 0.0,
                "reason": "LLM verification budget is exhausted.",
                "sources": source_reports,
                "verification_skipped": True,
            }

        text, error = provider.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=max_tokens,
            model=model,
        )

        parsed = _parse_verifier_response(parser, text) if not error else None

        if parsed is None:
            source_reports.append({
                "source_id": source_id,
                "judgment": "insufficient_evidence",
                "confidence": 0.0,
                "reason": error or "Verifier returned an invalid response.",
                "passages": passages,
            })
            source_verdicts.append("insufficient_evidence")
            continue

        source_reports.append({
            "source_id": source_id,
            **parsed,
            "passages": passages,
        })
        source_verdicts.append(parsed["judgment"])

    if not source_reports:
        return {
            "judgment": "insufficient_evidence",
            "confidence": 0.0,
            "reason": "No usable cited source was available for verification.",
            "sources": [],
            "verification_skipped": True,
        }

    supported = any(value == "supported" for value in source_verdicts)
    contradicted = any(value == "contradicted" for value in source_verdicts)

    if supported and contradicted:
        return {
            "judgment": "insufficient_evidence",
            "confidence": 0.0,
            "reason": "Cited sources produced conflicting semantic judgments.",
            "sources": source_reports,
            "verification_skipped": False,
            "source_conflict": True,
        }

    preferred = "supported" if supported else "contradicted" if contradicted else "insufficient_evidence"
    matches = [
        report
        for report in source_reports
        if report.get("judgment") == preferred
    ]
    best = max(
        matches,
        key=lambda report: float(report.get("confidence", 0.0)),
    ) if matches else None

    return {
        "judgment": preferred,
        "confidence": float(best.get("confidence", 0.0)) if best else max(
            float(report.get("confidence", 0.0))
            for report in source_reports
        ),
        "reason": (
            str(best.get("reason", ""))
            if best
            else "Cited passages did not establish or contradict the claim."
        ),
        "sources": source_reports,
        "verification_skipped": False,
        "source_conflict": False,
    }
