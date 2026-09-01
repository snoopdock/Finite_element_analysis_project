#!/usr/bin/env python3
"""Bounded persistence for semantic concept-relationship proposals."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Iterable


def _clean_ids(values: Iterable[Any]) -> list[str]:
    result = []
    seen = set()
    for value in values or []:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def proposal_id(concept_ids: Iterable[Any], relationship: str) -> str:
    """Return a deterministic proposal identity for one concept pair and relation."""
    ids = sorted(_clean_ids(concept_ids))
    relation = str(relationship or "insufficient_evidence").strip().lower()
    payload = "|".join(ids + [relation])
    return "relprop-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def record_proposal(
    state: Dict[str, Any],
    result: Dict[str, Any],
    *,
    max_records: int = 200,
) -> bool:
    """Persist one analyzer result as a non-authoritative relationship candidate."""
    if not isinstance(state, dict) or not isinstance(result, dict) or result.get("skipped"):
        return False

    graph = state.setdefault("knowledge_graph", {})
    if not isinstance(graph, dict):
        return False

    concept_ids = _clean_ids(result.get("concept_ids", []))
    proposal = result.get("proposal", {})
    if len(concept_ids) != 2 or not isinstance(proposal, dict):
        return False

    relationship = str(proposal.get("relationship", "insufficient_evidence")).strip().lower()
    if relationship == "insufficient_evidence":
        return False

    candidate_key = proposal_id(concept_ids, relationship)
    candidates = graph.setdefault("relationship_candidates", {})
    if not isinstance(candidates, dict):
        return False

    current = candidates.get(candidate_key, {})
    record = {
        **(current if isinstance(current, dict) else {}),
        "candidate_id": candidate_key,
        "source_id": concept_ids[0],
        "target_id": concept_ids[1],
        "type": relationship,
        "source_ids": _clean_ids(proposal.get("source_ids", result.get("source_ids", []))),
        "confidence": max(0.0, min(1.0, float(proposal.get("confidence", 0.0) or 0.0))),
        "reason": str(proposal.get("reason", "")).strip(),
        "proposition_ids": _clean_ids(result.get("proposition_ids", [])),
        "status": current.get("status", "candidate") if isinstance(current, dict) else "candidate",
    }
    candidates[candidate_key] = record

    if max_records >= 0 and len(candidates) > int(max_records):
        ordered = sorted(candidates.items(), key=lambda item: item[0])
        for key, _ in ordered[:-int(max_records)]:
            candidates.pop(key, None)
    return True


def record_proposals(
    state: Dict[str, Any],
    results: Iterable[Dict[str, Any]],
    *,
    max_records: int = 200,
) -> int:
    count = 0
    for result in results or []:
        count += int(record_proposal(state, result, max_records=max_records))
    return count
