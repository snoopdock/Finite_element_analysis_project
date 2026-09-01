#!/usr/bin/env python3
"""Bounded semantic analysis of candidate scientific concept relationships."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

_ALLOWED = {
    "subconcept_of",
    "specializes",
    "generalizes",
    "alternative_to",
    "complements",
    "related_to",
    "insufficient_evidence",
}

_ALIASES = {
    "subconcept": "subconcept_of",
    "subconcept_of": "subconcept_of",
    "specializes": "specializes",
    "generalizes": "generalizes",
    "alternative": "alternative_to",
    "alternative_to": "alternative_to",
    "complementary": "complements",
    "complements": "complements",
    "related": "related_to",
    "related_to": "related_to",
    "insufficient": "insufficient_evidence",
    "insufficient_evidence": "insufficient_evidence",
}

_SYSTEM_PROMPT = """You are a cautious scientific ontology analyst.

Given CONCEPT A and CONCEPT B plus propositions/evidence associated with them, infer only
whether the supplied evidence supports a relationship between the concepts.
Do not use name similarity as proof. Do not invent definitions, hierarchy, or provenance.
If the evidence does not distinguish the relationship, return insufficient_evidence.
For directional relations, distinguish generalizes from specializes carefully.
Use alternative_to or complements when concepts are distinct approaches that are not
hierarchical. Use related_to only when a meaningful relation is supported but more specific
classification is not justified.

Return ONLY valid JSON:
{
  "relationship": "subconcept_of" | "specializes" | "generalizes" |
                   "alternative_to" | "complements" | "related_to" |
                   "insufficient_evidence",
  "confidence": 0.0,
  "reason": "brief evidence-based explanation",
  "source_ids": []
}
"""


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _clean_ids(value: object) -> List[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    result: List[str] = []
    seen = set()
    for item in value:
        text = _clean(item)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def normalize_relationship_proposal(value: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    raw_relation = _clean(raw.get("relationship", "insufficient_evidence")).lower()
    relation = _ALIASES.get(raw_relation, "insufficient_evidence")
    try:
        confidence = max(0.0, min(1.0, float(raw.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "relationship": relation,
        "confidence": round(confidence, 4),
        "reason": _clean(raw.get("reason", "")),
        "source_ids": _clean_ids(raw.get("source_ids", [])),
    }


def analyze_concept_relationship(
    concept_a: Dict[str, Any],
    concept_b: Dict[str, Any],
    propositions: List[Dict[str, Any]],
    provider,
    parser,
    *,
    model: Optional[str] = None,
    max_tokens: int = 650,
) -> Dict[str, Any]:
    """Analyze one concept pair using bounded source-backed context."""
    source_ids = sorted({
        str(source_id)
        for proposition in propositions or []
        if isinstance(proposition, dict)
        for source_id in proposition.get("source_ids", []) or []
        if str(source_id).strip()
    })

    provenance = {
        "concept_ids": [
            concept_a.get("concept_id"),
            concept_b.get("concept_id"),
        ],
        "source_ids": source_ids,
    }

    if not concept_a.get("concept_id") or not concept_b.get("concept_id"):
        return {
            **provenance,
            "proposal": normalize_relationship_proposal({}),
            "skipped": True,
            "reason": "Missing concept identity.",
        }
    if not propositions:
        return {
            **provenance,
            "proposal": normalize_relationship_proposal({}),
            "skipped": True,
            "reason": "No source-backed propositions supplied.",
        }
    if provider.budget_exhausted():
        return {
            **provenance,
            "proposal": normalize_relationship_proposal({}),
            "skipped": True,
            "reason": "LLM budget exhausted.",
        }

    evidence = []
    for proposition in propositions[:8]:
        if not isinstance(proposition, dict):
            continue
        evidence.append({
            "proposition_id": proposition.get("proposition_id"),
            "statement": _clean(proposition.get("statement", "")),
            "source_ids": _clean_ids(proposition.get("source_ids", [])),
            "context": proposition.get("context", {}) if isinstance(proposition.get("context", {}), dict) else {},
        })

    prompt = (
        "CONCEPT A:\n" + _clean(concept_a.get("name", "")) +
        "\nTYPE A:\n" + _clean(concept_a.get("type", "")) +
        "\n\nCONCEPT B:\n" + _clean(concept_b.get("name", "")) +
        "\nTYPE B:\n" + _clean(concept_b.get("type", "")) +
        "\n\nSOURCE-BACKED PROPOSITIONS:\n" +
        json.dumps(evidence, ensure_ascii=False)
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
        return {
            **provenance,
            "proposal": normalize_relationship_proposal({}),
            "skipped": True,
            "reason": error or "Empty response.",
        }

    try:
        parsed = parser.parse(text, model_name="concept_relationship_analyzer")
    except Exception:
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = {}
    if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
        parsed = parsed[0]
    proposal = normalize_relationship_proposal(parsed)
    proposal["source_ids"] = sorted(set(proposal["source_ids"]) | set(source_ids))

    return {
        **provenance,
        "proposal": proposal,
        "skipped": False,
        "reason": "",
    }
