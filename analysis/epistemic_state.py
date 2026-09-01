#!/usr/bin/env python3
"""Structured epistemic status for propositions and relationships."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

EPISTEMIC_STATUSES = {
    "established",
    "supported",
    "conditional",
    "disputed",
    "alternative",
    "insufficient_evidence",
    "superseded",
    "unresolved",
    "unknown",
}

EVIDENCE_STRENGTHS = {"weak", "moderate", "strong", "unknown"}
LITERATURE_AGREEMENT = {"consensus", "mostly_agree", "mixed", "isolated", "unknown"}


@dataclass(frozen=True)
class EpistemicState:
    status: str = "unknown"
    evidence_strength: str = "unknown"
    literature_agreement: str = "unknown"
    model_confidence: float | None = None
    independent_support: str = "unknown"
    limitations: List[str] | None = None

    def normalized(self) -> Dict[str, Any]:
        return normalize_epistemic_state(self)


def _confidence(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


def _label(value: Any, allowed: set[str], default: str) -> str:
    normalized = str(value or default).strip().lower()
    return normalized if normalized in allowed else default


def normalize_epistemic_state(value: Any) -> Dict[str, Any]:
    if isinstance(value, EpistemicState):
        source = {
            "status": value.status,
            "evidence_strength": value.evidence_strength,
            "literature_agreement": value.literature_agreement,
            "model_confidence": value.model_confidence,
            "independent_support": value.independent_support,
            "limitations": value.limitations,
        }
    elif isinstance(value, dict):
        source = value
    else:
        source = {}

    limitations = []
    seen = set()
    for item in source.get("limitations", []) or []:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            limitations.append(text)

    return {
        "status": _label(source.get("status"), EPISTEMIC_STATUSES, "unknown"),
        "evidence_strength": _label(source.get("evidence_strength"), EVIDENCE_STRENGTHS, "unknown"),
        "literature_agreement": _label(source.get("literature_agreement"), LITERATURE_AGREEMENT, "unknown"),
        "model_confidence": _confidence(source.get("model_confidence")),
        "independent_support": str(source.get("independent_support") or "unknown").strip(),
        "limitations": limitations,
    }
