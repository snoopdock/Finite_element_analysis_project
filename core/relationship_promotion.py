#!/usr/bin/env python3
"""Conservative promotion of relationship candidates to authoritative edges."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from core.graph_repository import upsert_relationship


def _clean_ids(values: Iterable[Any]) -> list[str]:
    result = []
    seen = set()
    for value in values or []:
        value = str(value).strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def promote_candidate(
    state: Dict[str, Any],
    candidate_id: str,
    verification: Dict[str, Any],
) -> Optional[str]:
    """Promote one candidate only when explicitly verified with source provenance."""
    if not isinstance(state, dict) or not isinstance(verification, dict):
        return None
    if str(verification.get("status", "")).strip().lower() != "verified":
        return None

    graph = state.get("knowledge_graph", {})
    candidates = graph.get("relationship_candidates", {}) if isinstance(graph, dict) else {}
    candidate = candidates.get(str(candidate_id)) if isinstance(candidates, dict) else None
    if not isinstance(candidate, dict):
        return None

    source_ids = _clean_ids(verification.get("source_ids", []))
    if not source_ids:
        return None

    if str(verification.get("type", "")).strip() != str(candidate.get("type", "")).strip():
        return None

    relationship_id = upsert_relationship(
        graph,
        source_id=str(candidate.get("source_id", "")),
        target_id=str(candidate.get("target_id", "")),
        relation_type=str(candidate.get("type", "related_to")),
        source_ids=source_ids,
        confidence=float(verification.get("confidence", 0.0) or 0.0),
        reason=str(verification.get("reason", "")).strip(),
    )
    if not relationship_id:
        return None

    candidate["status"] = "promoted"
    candidate["relationship_id"] = relationship_id
    candidate["verification"] = {
        "source_ids": source_ids,
        "confidence": max(0.0, min(1.0, float(verification.get("confidence", 0.0) or 0.0))),
        "reason": str(verification.get("reason", "")).strip(),
    }
    return relationship_id
