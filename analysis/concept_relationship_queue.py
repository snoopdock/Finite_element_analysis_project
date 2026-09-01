#!/usr/bin/env python3
"""Deterministic queueing of unverified concept-relationship candidates."""

from __future__ import annotations

from typing import Any, Dict, List


def verification_queue(
    state: Dict[str, Any],
    *,
    max_tasks: int = 8,
) -> List[Dict[str, Any]]:
    """Return bounded verification tasks for unresolved relationship candidates."""
    graph = state.get("knowledge_graph", {}) if isinstance(state, dict) else {}
    candidates = graph.get("relationship_candidates", {}) if isinstance(graph, dict) else {}
    if not isinstance(candidates, dict):
        return []

    tasks = []
    for candidate_id, candidate in candidates.items():
        if not isinstance(candidate, dict):
            continue
        if str(candidate.get("status", "candidate")).strip().lower() != "candidate":
            continue
        source_id = str(candidate.get("source_id", "")).strip()
        target_id = str(candidate.get("target_id", "")).strip()
        relation_type = str(candidate.get("type", "")).strip()
        if not source_id or not target_id or not relation_type:
            continue

        try:
            confidence = max(0.0, min(1.0, float(candidate.get("confidence", 0.0))))
        except (TypeError, ValueError):
            confidence = 0.0

        tasks.append({
            "candidate_id": str(candidate_id),
            "source_id": source_id,
            "target_id": target_id,
            "type": relation_type,
            "source_ids": list(candidate.get("source_ids", []) or []),
            "proposition_ids": list(candidate.get("proposition_ids", []) or []),
            "confidence": confidence,
            "reason": str(candidate.get("reason", "")).strip(),
        })

    tasks.sort(key=lambda item: (item["confidence"], item["candidate_id"]))
    return tasks[: max(0, int(max_tasks))]
