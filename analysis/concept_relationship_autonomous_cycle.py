#!/usr/bin/env python3
"""Opt-in bounded relationship-validation cycle for the scientific graph."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from analysis.concept_relationship_verification_cycle import run_verification_cycle
from analysis.concept_relationship_promotion_adapter import promote_verified_result


def run_autonomous_relationship_cycle(
    state: Dict[str, Any],
    provider,
    parser,
    *,
    enabled: bool = False,
    max_tasks: int = 4,
    model: Optional[str] = None,
    max_tokens: int = 650,
    minimum_confidence: float = 0.70,
) -> Dict[str, Any]:
    """Run bounded verification and optional promotion without rewriting content."""
    if not enabled:
        result = {"enabled": False, "queued": 0, "verified": 0, "rejected": 0,
                  "insufficient_evidence": 0, "skipped": 0, "promoted": 0, "results": []}
        if isinstance(state, dict):
            state["last_concept_relationship_autonomous_cycle"] = {
                key: value for key, value in result.items() if key != "results"
            }
        return result

    verification = run_verification_cycle(
        state,
        provider,
        parser,
        max_tasks=max(0, int(max_tasks)),
        model=model,
        max_tokens=max(1, int(max_tokens)),
        minimum_confidence=minimum_confidence,
    )

    promoted = 0
    promotion_results: List[str] = []
    for result in verification.get("results", []) or []:
        relationship_id = promote_verified_result(state, result)
        if relationship_id:
            promoted += 1
            promotion_results.append(str(relationship_id))

    output = {
        "enabled": True,
        "queued": verification.get("queued", 0),
        "verified": verification.get("verified", 0),
        "rejected": verification.get("rejected", 0),
        "insufficient_evidence": verification.get("insufficient_evidence", 0),
        "skipped": verification.get("skipped", 0),
        "promoted": promoted,
        "promoted_relationship_ids": promotion_results,
        "results": verification.get("results", []),
    }
    if isinstance(state, dict):
        state["last_concept_relationship_autonomous_cycle"] = {
            key: value for key, value in output.items() if key != "results"
        }
    return output
