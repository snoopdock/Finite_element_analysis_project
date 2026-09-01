#!/usr/bin/env python3
"""Source-backed verification of one proposed scientific concept relationship."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from analysis.concept_relationship_analyzer import analyze_concept_relationship

_ALLOWED_DECISIONS = {"verified", "rejected", "insufficient_evidence"}


_REJECTION_MAP = {
    "insufficient_evidence": "insufficient_evidence",
}


def _clean_ids(values: Any) -> List[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    result: List[str] = []
    seen = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def normalize_verification(value: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    decision = str(raw.get("decision", "insufficient_evidence")).strip().lower()
    if decision not in _ALLOWED_DECISIONS:
        decision = "insufficient_evidence"
    try:
        confidence = max(0.0, min(1.0, float(raw.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "decision": decision,
        "confidence": round(confidence, 4),
        "reason": str(raw.get("reason", "")).strip(),
        "source_ids": _clean_ids(raw.get("source_ids", [])),
        "proposition_ids": _clean_ids(raw.get("proposition_ids", [])),
    }


def verify_candidate_relationship(
    state: Dict[str, Any],
    task: Dict[str, Any],
    provider,
    parser,
    *,
    model: Optional[str] = None,
    max_tokens: int = 650,
    minimum_confidence: float = 0.70,
) -> Dict[str, Any]:
    """Verify a candidate only from its existing source-backed propositions."""
    graph = state.get("knowledge_graph", {}) if isinstance(state, dict) else {}
    concepts = graph.get("concepts", {}) if isinstance(graph, dict) else {}
    propositions = graph.get("propositions", {}) if isinstance(graph, dict) else {}

    source_id = str(task.get("source_id", "")).strip()
    target_id = str(task.get("target_id", "")).strip()
    expected_type = str(task.get("type", "")).strip()
    proposition_ids = _clean_ids(task.get("proposition_ids", []))

    provenance = {
        "candidate_id": str(task.get("candidate_id", "")),
        "concept_ids": [source_id, target_id],
        "proposition_ids": proposition_ids,
    }

    if not isinstance(concepts, dict) or source_id not in concepts or target_id not in concepts:
        return {**provenance, "verification": normalize_verification({}), "skipped": True, "reason": "Missing concept endpoint."}

    if expected_type not in {
        "subconcept_of",
        "specializes",
        "generalizes",
        "alternative_to",
        "complements",
        "related_to",
    }:
        return {**provenance, "verification": normalize_verification({}), "skipped": True, "reason": "Unsupported candidate relationship type."}

    selected = []
    for proposition_id in proposition_ids:
        proposition = propositions.get(proposition_id) if isinstance(propositions, dict) else None
        if isinstance(proposition, dict):
            selected.append(proposition)
    if not selected:
        return {**provenance, "verification": normalize_verification({}), "skipped": True, "reason": "No source-backed propositions for candidate."}

    if provider.budget_exhausted():
        return {**provenance, "verification": normalize_verification({}), "skipped": True, "reason": "LLM budget exhausted."}

    analysis = analyze_concept_relationship(
        concepts[source_id],
        concepts[target_id],
        selected,
        provider,
        parser,
        model=model,
        max_tokens=max_tokens,
    )
    if analysis.get("skipped"):
        return {**provenance, "verification": normalize_verification({}), "skipped": True, "reason": analysis.get("reason", "Analysis skipped.")}

    proposal = analysis.get("proposal", {})
    relationship = str(proposal.get("relationship", "insufficient_evidence")).strip().lower()
    confidence = float(proposal.get("confidence", 0.0) or 0.0)
    proposed_sources = _clean_ids(proposal.get("source_ids", []))
    task_sources = _clean_ids(task.get("source_ids", []))

    if relationship == expected_type and confidence >= max(0.0, min(1.0, float(minimum_confidence))) and proposed_sources:
        decision = "verified"
    elif relationship == "insufficient_evidence" or confidence < max(0.0, min(1.0, float(minimum_confidence))):
        decision = "insufficient_evidence"
    else:
        decision = "rejected"

    verification = normalize_verification({
        "decision": decision,
        "confidence": confidence,
        "reason": proposal.get("reason", ""),
        "source_ids": sorted(set(task_sources) | set(proposed_sources)),
        "proposition_ids": proposition_ids,
    })

    return {
        **provenance,
        "expected_type": expected_type,
        "analysis": analysis,
        "verification": verification,
        "skipped": False,
        "reason": "",
    }
