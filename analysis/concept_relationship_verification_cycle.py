#!/usr/bin/env python3
"""Bounded verification cycle for proposed scientific concept relationships."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from analysis.concept_relationship_queue import verification_queue
from analysis.concept_relationship_verifier import verify_candidate_relationship


def run_verification_cycle(
    state: Dict[str, Any],
    provider,
    parser,
    *,
    max_tasks: int = 4,
    model: Optional[str] = None,
    max_tokens: int = 650,
    minimum_confidence: float = 0.70,
) -> Dict[str, Any]:
    """Verify a bounded queue and persist only verification results."""
    tasks = verification_queue(state, max_tasks=max(0, int(max_tasks)))
    results: List[Dict[str, Any]] = []
    skipped = 0

    for task in tasks:
        result = verify_candidate_relationship(
            state,
            task,
            provider,
            parser,
            model=model,
            max_tokens=max_tokens,
            minimum_confidence=minimum_confidence,
        )
        if result.get("skipped"):
            skipped += 1
            continue
        results.append(result)

    state["last_concept_relationship_verification"] = {
        "queued": len(tasks),
        "verified": sum(1 for item in results if item.get("verification", {}).get("decision") == "verified"),
        "rejected": sum(1 for item in results if item.get("verification", {}).get("decision") == "rejected"),
        "insufficient_evidence": sum(
            1 for item in results
            if item.get("verification", {}).get("decision") == "insufficient_evidence"
        ),
        "skipped": skipped,
    }
    return {
        "queued": len(tasks),
        "verified": sum(1 for item in results if item.get("verification", {}).get("decision") == "verified"),
        "rejected": sum(1 for item in results if item.get("verification", {}).get("decision") == "rejected"),
        "insufficient_evidence": sum(
            1 for item in results
            if item.get("verification", {}).get("decision") == "insufficient_evidence"
        ),
        "skipped": skipped,
        "results": results,
    }
