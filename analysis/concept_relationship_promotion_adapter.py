#!/usr/bin/env python3
"""Adapt Stage 7 verification results to the existing graph promotion gate."""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.relationship_promotion import promote_candidate


def verification_to_promotion_record(result: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a verification result without changing its scientific meaning."""
    verification = result.get("verification", {}) if isinstance(result, dict) else {}
    if not isinstance(verification, dict):
        verification = {}
    return {
        "status": verification.get("decision", "insufficient_evidence"),
        "type": result.get("expected_type", ""),
        "source_ids": list(verification.get("source_ids", []) or []),
        "confidence": verification.get("confidence", 0.0),
        "reason": verification.get("reason", ""),
    }


def promote_verified_result(
    state: Dict[str, Any],
    result: Dict[str, Any],
) -> Optional[str]:
    """Promote only a verified result through the existing explicit gate."""
    if not isinstance(result, dict):
        return None
    if str(result.get("verification", {}).get("decision", "")).strip().lower() != "verified":
        return None
    candidate_id = str(result.get("candidate_id", "")).strip()
    if not candidate_id:
        return None
    return promote_candidate(
        state,
        candidate_id,
        verification_to_promotion_record(result),
    )
