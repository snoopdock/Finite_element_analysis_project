#!/usr/bin/env python3
"""Deterministic policy for prioritizing OAA adjustments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional


@dataclass(frozen=True)
class AdjustmentScore:
    """Scoring breakdown for one actionable anomaly."""

    key: str
    anomaly_type: str
    severity: float
    persistence: float
    cost: float
    score: float


@dataclass(frozen=True)
class AdjustmentDecision:
    """Immutable, auditable OAA action selection."""

    key: str
    anomaly_type: str
    action: str
    section_id: Optional[str]
    score: AdjustmentScore

    def to_dict(self) -> Dict:
        """Return a JSON-serializable action decision record."""
        return {
            "key": self.key,
            "anomaly_type": self.anomaly_type,
            "action": self.action,
            "section_id": self.section_id,
            "score": {
                "severity": self.score.severity,
                "persistence": self.score.persistence,
                "cost": self.score.cost,
                "score": self.score.score,
            },
        }


class OAAActionPolicy:
    """Rank actionable anomalies without performing any mutation or LLM call."""

    DEFAULT_SEVERITY = {
        "repetition": 1.00,
        "too_simple": 0.95,
        "merge_candidate": 0.85,
        "length_imbalance": 0.65,
        "missing_transition": 0.55,
    }

    DEFAULT_COST = {
        "merge_candidate": 0.85,
        "too_simple": 0.75,
        "repetition": 0.45,
        "length_imbalance": 0.40,
        "missing_transition": 0.35,
    }

    def __init__(
        self,
        severity_weights: Optional[Dict[str, float]] = None,
        cost_weights: Optional[Dict[str, float]] = None,
        persistence_weight: float = 0.35,
        severity_weight: float = 0.50,
        cost_weight: float = 0.15,
    ) -> None:
        self.severity_weights = dict(
            self.DEFAULT_SEVERITY
        )
        if severity_weights:
            self.severity_weights.update(severity_weights)

        self.cost_weights = dict(
            self.DEFAULT_COST
        )
        if cost_weights:
            self.cost_weights.update(cost_weights)

        total = (
            float(persistence_weight)
            + float(severity_weight)
            + float(cost_weight)
        )
        if total <= 0.0:
            raise ValueError("OAA action-policy weights must sum to a positive value.")

        self.persistence_weight = float(persistence_weight) / total
        self.severity_weight = float(severity_weight) / total
        self.cost_weight = float(cost_weight) / total

    @staticmethod
    def _normalize(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    def score(
        self,
        anomaly: Dict,
        persistence_count: int = 0,
    ) -> AdjustmentScore:
        anomaly_type = str(
            anomaly.get(
                "type",
                "",
            )
        )
        key = str(
            anomaly.get(
                "key",
                "",
            )
        )

        severity = self._normalize(
            self.severity_weights.get(
                anomaly_type,
                0.5,
            )
        )

        persistence = self._normalize(
            persistence_count / 5.0
        )

        cost = self._normalize(
            self.cost_weights.get(
                anomaly_type,
                0.5,
            )
        )

        score = (
            self.persistence_weight * persistence
            + self.severity_weight * severity
            + self.cost_weight * (1.0 - cost)
        )

        return AdjustmentScore(
            key=key,
            anomaly_type=anomaly_type,
            severity=severity,
            persistence=persistence,
            cost=cost,
            score=score,
        )

    def rank(
        self,
        anomalies: Iterable[Dict],
        persistence_counts: Optional[Dict[str, int]] = None,
    ) -> List[Dict]:
        persistence_counts = persistence_counts or {}
        scored = []

        for anomaly in anomalies or []:
            if not isinstance(anomaly, dict):
                continue
            score = self.score(
                anomaly,
                persistence_counts.get(
                    str(anomaly.get("key", "")),
                    0,
                ),
            )
            enriched = dict(anomaly)
            enriched["adjustment_score"] = {
                "score": score.score,
                "severity": score.severity,
                "persistence": score.persistence,
                "cost": score.cost,
            }
            scored.append(enriched)

        scored.sort(
            key=lambda anomaly: (
                -float(
                    anomaly["adjustment_score"]["score"]
                ),
                str(anomaly.get("type", "")),
                str(anomaly.get("key", "")),
            )
        )
        return scored

    def choose(self, anomalies: Iterable[Dict], persistence_counts: Optional[Dict[str, int]] = None) -> Optional[AdjustmentDecision]:
        """Return the highest-ranked action as an immutable decision."""
        ranked = self.rank(anomalies, persistence_counts)
        if not ranked:
            return None

        selected = ranked[0]
        score_data = selected.get("adjustment_score", {})
        score = AdjustmentScore(
            key=str(selected.get("key", "")),
            anomaly_type=str(selected.get("type", "")),
            severity=self._normalize(score_data.get("severity", 0.0)),
            persistence=self._normalize(score_data.get("persistence", 0.0)),
            cost=self._normalize(score_data.get("cost", 0.0)),
            score=self._normalize(score_data.get("score", 0.0)),
        )
        return AdjustmentDecision(
            key=score.key,
            anomaly_type=score.anomaly_type,
            action=str(selected.get("action", "")),
            section_id=(
                str(selected.get("section_id"))
                if selected.get("section_id") is not None
                else None
            ),
            score=score,
        )
