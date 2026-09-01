#!/usr/bin/env python3
"""Non-scalar scientific attention signals for scheduling research and writing."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict


@dataclass(frozen=True)
class ScientificAttention:
    """Separate reasons a section/proposition may need additional attention."""

    evidence_gap: float = 0.0
    disagreement: float = 0.0
    contextual_complexity: float = 0.0
    verification_need: float = 0.0
    importance: float = 0.0
    decision_consequence: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


def _clamp(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def normalize_attention(value: Any) -> Dict[str, float]:
    if isinstance(value, ScientificAttention):
        return value.to_dict()
    if not isinstance(value, dict):
        return ScientificAttention().to_dict()
    return ScientificAttention(
        evidence_gap=_clamp(value.get("evidence_gap")),
        disagreement=_clamp(value.get("disagreement")),
        contextual_complexity=_clamp(value.get("contextual_complexity")),
        verification_need=_clamp(value.get("verification_need")),
        importance=_clamp(value.get("importance")),
        decision_consequence=_clamp(value.get("decision_consequence")),
    ).to_dict()


def attention_priority(attention: Dict[str, Any]) -> float:
    """Return a bounded scheduling score without collapsing the stored signals."""
    values = normalize_attention(attention)
    weights = {
        "evidence_gap": 0.25,
        "disagreement": 0.20,
        "contextual_complexity": 0.15,
        "verification_need": 0.20,
        "importance": 0.15,
        "decision_consequence": 0.05,
    }
    return max(0.0, min(1.0, sum(values[key] * weight for key, weight in weights.items())))
