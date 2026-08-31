#!/usr/bin/env python3
"""Policy-aware adapter for DynamicWriter.

This adapter integrates ``WritingDecisionPolicy`` without changing the
existing paragraph/outline generation implementation. It keeps the section
objects available to the policy so UUIDs and lineage remain intact.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from analysis.writing_policy import WritingDecisionPolicy
from writing.dynamic_writer import DynamicWriter


class PolicyAwareDynamicWriter(DynamicWriter):
    """DynamicWriter with explicit Stage 2 scheduling/model policy."""

    def __init__(
        self,
        provider,
        parser,
        config,
        iteration_history,
        writing_indicator=None,
    ):
        super().__init__(
            provider,
            parser,
            config,
            iteration_history,
            writing_indicator=writing_indicator,
        )

        writing_config = config.get("writing", {})

        self.decision_policy = WritingDecisionPolicy(
            theta=writing_config.get(
                "theta",
                0.75,
            ),
            tau=writing_config.get(
                "tau",
                0.60,
            ),
        )

        self._decision_sections: List[Dict] = []

    def mark_sections(
        self,
        section_topics: List[str],
    ) -> List[str]:
        """Schedule sections using the explicit policy."""
        sections = list(self._decision_sections)

        if not sections:
            # Preserve the existing bootstrap behavior when there are no
            # materialized section objects yet.
            return super().mark_sections(
                section_topics
            )

        ranked = self.decision_policy.rank_sections(
            sections,
            self.indicator,
            self.history,
        )

        selected = self.decision_policy.select_sections(
            ranked
        )

        selected_ids = {
            str(section.get("section_id"))
            for section, _ in selected
            if section.get("section_id")
        }

        selected_titles = []

        for section in sections:
            section_id = section.get(
                "section_id"
            )
            title = str(
                section.get("title", "")
            ).strip()

            if (
                section_id
                and str(section_id) in selected_ids
            ):
                selected_titles.append(title)

        # Include configured topics which are not yet materialized as
        # sections, because they still need initial generation.
        materialized_titles = {
            str(section.get("title", "")).strip()
            for section in sections
        }

        for topic in section_topics:
            if not topic:
                continue
            if topic not in materialized_titles:
                selected_titles.append(topic)

        return selected_titles

    def select_model(self, eta: float) -> str:
        """Select the model through the shared Stage 2 policy."""
        models = self.config.get(
            "cloudflare_models",
            ["@cf/meta/llama-3.1-8b-instruct"],
        )

        if not isinstance(models, list) or not models:
            raise RuntimeError(
                "cloudflare_models must contain at least one model."
            )

        index = self.decision_policy.select_model_index(
            eta,
            models,
        )

        return str(models[index])

    def run(
        self,
        section_topics: List[str],
        kb: Dict,
        existing_sections: List[Dict],
        errors: List[str],
    ) -> Tuple[List[Dict], int]:
        self._decision_sections = [
            section
            for section in existing_sections
            if isinstance(section, dict)
        ]

        try:
            return super().run(
                section_topics,
                kb,
                existing_sections,
                errors,
            )
        finally:
            self._decision_sections = []
