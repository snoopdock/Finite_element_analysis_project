#!/usr/bin/env python3
"""Explicit writing decision policy.

The policy separates section priority, processing selection, and model
selection. It is deterministic and contains no LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class SectionDecision:
    """Immutable, auditable decision metadata for one section."""

    section_id: Optional[str]
    title: str
    eta: float
    priority: float
    selected: bool
    model_index: int
    model: str

    def validate(self, models: Sequence[str]) -> None:
        """Raise ValueError if the decision record is internally inconsistent."""
        if self.section_id is not None and not str(self.section_id).strip():
            raise ValueError("section_id must be None or non-empty.")
        if not str(self.title).strip():
            raise ValueError("title must be non-empty.")
        if not 0.0 <= float(self.eta) <= 1.0:
            raise ValueError("eta must be in [0, 1].")
        if float(self.priority) < 0.0:
            raise ValueError("priority must be non-negative.")
        if not isinstance(self.selected, bool):
            raise ValueError("selected must be boolean.")
        if not models:
            raise ValueError("At least one model is required.")
        if not 0 <= int(self.model_index) < len(models):
            raise ValueError("model_index is outside the supplied model list.")
        if str(self.model) != str(models[self.model_index]):
            raise ValueError("model does not match model_index.")

    def to_dict(self, models: Sequence[str]) -> dict[str, Any]:
        """Return a JSON-serializable audit record after validation."""
        self.validate(models)
        return {
            "section_id": self.section_id,
            "title": self.title,
            "eta": float(self.eta),
            "priority": float(self.priority),
            "selected": bool(self.selected),
            "model_index": int(self.model_index),
            "model": self.model,
        }


class WritingDecisionPolicy:
    """Deterministic policy for section scheduling and model selection."""

    def __init__(
        self,
        theta: float = 0.75,
        tau: float = 0.60,
        high_eta_model_index: int = 0,
        low_eta_model_index: int = -1,
    ) -> None:
        self.theta = min(1.0, max(0.0, float(theta)))
        self.tau = min(1.0, max(0.0, float(tau)))
        self.high_eta_model_index = int(high_eta_model_index)
        self.low_eta_model_index = int(low_eta_model_index)

    @staticmethod
    def _eta(section_or_topic, indicator, history) -> float:
        """Compute eta through the supplied indicator."""
        value = indicator.compute(section_or_topic, history)
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _semantic_priority(section: dict) -> float:
        """Return a bounded priority multiplier from scientific review feedback."""
        feedback = section.get("semantic_feedback", {})
        if not isinstance(feedback, dict):
            return 1.0

        action = str(feedback.get("action", "retain"))
        confidence = feedback.get("confidence", 0.0)
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = 0.0

        if action == "analyze_perspectives":
            # Disagreement increases attention; it does not imply that content
            # should be deleted or that one source must be declared correct.
            return 1.0 + 0.40 * confidence
        if action == "seek_more_evidence":
            return 1.0 + 0.25 * confidence
        return 1.0

    def _priority(self, section_or_topic, indicator, history) -> tuple[float, float]:
        """Return (base eta, feedback-adjusted priority)."""
        eta = self._eta(section_or_topic, indicator, history)
        if isinstance(section_or_topic, dict):
            priority = eta * self._semantic_priority(section_or_topic)
        else:
            priority = eta
        return eta, max(0.0, priority)

    def rank_sections(self, sections: Sequence, indicator, history) -> List[Tuple[object, float]]:
        """Return sections ordered by feedback-adjusted priority."""
        ranked: List[Tuple[object, float]] = []

        for section in sections or []:
            if not isinstance(section, dict):
                continue
            title = str(section.get("title", "")).strip()
            if not title:
                continue
            _, priority = self._priority(section, indicator, history)
            ranked.append((section, priority))

        ranked.sort(
            key=lambda pair: (
                -pair[1],
                str(pair[0].get("title", "")),
                str(pair[0].get("section_id", "")),
            )
        )
        return ranked

    def select_sections(self, ranked_sections: Sequence[Tuple[dict, float]]) -> List[Tuple[dict, float]]:
        """Select the smallest priority prefix reaching theta of total priority."""
        ranked = list(ranked_sections or [])
        if not ranked:
            return []

        total_priority = sum(priority for _, priority in ranked)
        if total_priority <= 0.0:
            return ranked[:2]

        target = self.theta * total_priority
        cumulative = 0.0
        selected = []
        for section, priority in ranked:
            selected.append((section, priority))
            cumulative += priority
            if cumulative >= target:
                break
        return selected

    @staticmethod
    def _normalize_model_index(index: int, models: Sequence[str]) -> int:
        count = len(models)
        if count <= 0:
            raise ValueError("At least one model is required.")
        index = int(index)
        if index < 0:
            index = count + index
        return max(0, min(count - 1, index))

    def select_model_index(self, eta: float, models: Sequence[str]) -> int:
        """Select a configured model index from an explicit threshold policy."""
        if not models:
            raise ValueError("At least one model is required.")
        normalized_eta = max(0.0, min(1.0, float(eta)))
        if normalized_eta >= self.tau:
            return self._normalize_model_index(self.high_eta_model_index, models)
        return self._normalize_model_index(self.low_eta_model_index, models)

    def decide(
        self,
        sections: Sequence[dict],
        indicator,
        history,
        models: Sequence[str],
    ) -> List[SectionDecision]:
        """Produce deterministic, self-validating decisions for supplied sections."""
        ranked = self.rank_sections(sections, indicator, history)
        selected_items = self.select_sections(ranked)
        selected_ids = {
            str(section.get("section_id"))
            for section, _ in selected_items
            if section.get("section_id")
        }

        result = []
        for section, priority in ranked:
            section_id = section.get("section_id")
            title = str(section.get("title", "")).strip()
            eta = self._eta(section, indicator, history)

            selected = (
                str(section_id) in selected_ids
                if section_id
                else any(section is selected_section for selected_section, _ in selected_items)
            )

            model_index = self.select_model_index(eta, models)
            decision = SectionDecision(
                section_id=str(section_id) if section_id else None,
                title=title,
                eta=eta,
                priority=priority,
                selected=selected,
                model_index=model_index,
                model=str(models[model_index]),
            )
            decision.validate(models)
            result.append(decision)

        return result
