#!/usr/bin/env python3
"""Explicit writing decision policy.

Stage 2A separates three decisions that were previously coupled inside
DynamicWriter:

1. section priority: how strongly a section should be considered;
2. processing selection: whether a section belongs in the current cycle;
3. model selection: which configured model should handle the section.

This module is intentionally independent of the writer. It can therefore be
introduced and audited before changing the existing generation path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class SectionDecision:
    """Decision metadata for one section."""

    section_id: Optional[str]
    title: str
    eta: float
    priority: float
    selected: bool
    model_index: int
    model: str


class WritingDecisionPolicy:
    """Deterministic policy for section scheduling and model selection."""

    def __init__(
        self,
        theta: float = 0.75,
        tau: float = 0.60,
    ) -> None:
        self.theta = min(1.0, max(0.0, float(theta)))
        self.tau = min(1.0, max(0.0, float(tau)))

    @staticmethod
    def _eta(section_or_topic, indicator, history) -> float:
        """Compute eta through the supplied indicator."""
        value = indicator.compute(
            section_or_topic,
            history,
        )
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0

    def rank_sections(
        self,
        sections: Sequence,
        indicator,
        history,
    ) -> List[Tuple[object, float]]:
        """Return sections ordered by descending eta, then title.

        The original section objects are preserved so UUIDs and lineage stay
        attached to the scheduling decision.
        """
        ranked: List[Tuple[object, float]] = []

        for section in sections or []:
            if not isinstance(section, dict):
                continue

            title = str(section.get("title", "")).strip()
            if not title:
                continue

            eta = self._eta(
                section,
                indicator,
                history,
            )
            ranked.append((section, eta))

        ranked.sort(
            key=lambda pair: (
                -pair[1],
                str(pair[0].get("title", "")),
                str(pair[0].get("section_id", "")),
            )
        )
        return ranked

    def select_sections(
        self,
        ranked_sections: Sequence[Tuple[dict, float]],
    ) -> List[Tuple[dict, float]]:
        """Select the smallest prefix reaching theta of total eta.

        If all eta values are zero, select at most two sections to preserve
        the existing writer's bootstrap behavior.
        """
        ranked = list(ranked_sections or [])
        if not ranked:
            return []

        total_eta = sum(
            eta
            for _, eta in ranked
        )

        if total_eta <= 0.0:
            return ranked[:2]

        target = self.theta * total_eta
        cumulative = 0.0
        selected: List[Tuple[dict, float]] = []

        for section, eta in ranked:
            selected.append((section, eta))
            cumulative += eta
            if cumulative >= target:
                break

        return selected

    def select_model_index(
        self,
        eta: float,
        models: Sequence[str],
    ) -> int:
        """Select a configured model index without performing an LLM call.

        Stage 2A retains the existing binary threshold behavior deliberately;
        later Stage 2 work can replace this method with a richer model policy.
        """
        if not models:
            raise ValueError("At least one model is required.")

        if len(models) == 1:
            return 0

        normalized_eta = max(
            0.0,
            min(1.0, float(eta)),
        )

        return 0 if normalized_eta >= self.tau else len(models) - 1

    def decide(
        self,
        sections: Sequence[dict],
        indicator,
        history,
        models: Sequence[str],
    ) -> List[SectionDecision]:
        """Produce complete, deterministic decisions for the supplied sections."""
        ranked = self.rank_sections(
            sections,
            indicator,
            history,
        )
        selected_items = self.select_sections(ranked)
        selected_ids = {
            str(section.get("section_id"))
            for section, _ in selected_items
            if section.get("section_id")
        }

        result: List[SectionDecision] = []

        for section, eta in ranked:
            section_id = section.get("section_id")
            title = str(
                section.get("title", "")
            ).strip()
            selected = (
                str(section_id) in selected_ids
                if section_id
                else any(
                    section is selected_section
                    for selected_section, _ in selected_items
                )
            )

            model_index = self.select_model_index(
                eta,
                models,
            )

            result.append(
                SectionDecision(
                    section_id=(
                        str(section_id)
                        if section_id
                        else None
                    ),
                    title=title,
                    eta=eta,
                    priority=eta,
                    selected=selected,
                    model_index=model_index,
                    model=str(models[model_index]),
                )
            )

        return result
