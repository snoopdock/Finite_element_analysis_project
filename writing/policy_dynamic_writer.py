#!/usr/bin/env python3
"""Policy-aware adapter for DynamicWriter."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from analysis.writing_policy import WritingDecisionPolicy
from writing.dynamic_writer import DynamicWriter
from writing.output_validator import (
    WritingValidationError,
    validate_paragraph,
    validate_section_structure,
)


class PolicyAwareDynamicWriter(DynamicWriter):
    """DynamicWriter with explicit scheduling, model policy, and validation."""

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

        writing_config = config.get(
            "writing",
            {},
        )

        model_policy = writing_config.get(
            "model_selection",
            {},
        )

        self.decision_policy = WritingDecisionPolicy(
            theta=writing_config.get(
                "theta",
                0.75,
            ),
            tau=writing_config.get(
                "tau",
                0.60,
            ),
            high_eta_model_index=model_policy.get(
                "high_eta_model_index",
                0,
            ),
            low_eta_model_index=model_policy.get(
                "low_eta_model_index",
                -1,
            ),
        )

        self._decision_sections: List[Dict] = []
        self.last_decisions: List[Dict] = []

        self.min_paragraph_words = int(
            writing_config.get(
                "min_paragraph_words",
                20,
            )
        )

        self.max_paragraph_words: Optional[int] = writing_config.get(
            "max_paragraph_words"
        )

        if self.max_paragraph_words is not None:
            self.max_paragraph_words = int(
                self.max_paragraph_words
            )

    def mark_sections(
        self,
        section_topics: List[str],
    ) -> List[str]:
        """Schedule sections using the explicit policy."""
        sections = list(
            self._decision_sections
        )

        if not sections:
            selected = super().mark_sections(
                section_topics
            )
            self.last_decisions = [
                {
                    "section_id": None,
                    "title": topic,
                    "selected": True,
                }
                for topic in selected
            ]
            return selected

        ranked = self.decision_policy.rank_sections(
            sections,
            self.indicator,
            self.history,
        )

        selected = self.decision_policy.select_sections(
            ranked
        )

        models = self.config.get(
            "cloudflare_models",
            ["@cf/meta/llama-3.1-8b-instruct"],
        )

        decisions = self.decision_policy.decide(
            sections,
            self.indicator,
            self.history,
            models,
        )
        self.last_decisions = [
            decision.__dict__.copy()
            for decision in decisions
        ]

        selected_ids = {
            str(
                section.get(
                    "section_id"
                )
            )
            for section, _ in selected
            if section.get("section_id")
        }

        selected_titles = []

        for section in sections:
            section_id = section.get(
                "section_id"
            )

            title = str(
                section.get(
                    "title",
                    "",
                )
            ).strip()

            if (
                section_id
                and str(section_id) in selected_ids
            ):
                selected_titles.append(
                    title
                )

        materialized_titles = {
            str(
                section.get(
                    "title",
                    "",
                )
            ).strip()
            for section in sections
        }

        for topic in section_topics:
            if not topic:
                continue

            if topic not in materialized_titles:
                selected_titles.append(
                    topic
                )

        return selected_titles

    def select_model(
        self,
        eta: float,
    ) -> str:
        """Select the model through the Stage 2 policy."""
        models = self.config.get(
            "cloudflare_models",
            ["@cf/meta/llama-3.1-8b-instruct"],
        )

        if not isinstance(
            models,
            list,
        ) or not models:
            raise RuntimeError(
                "cloudflare_models must contain at least one model."
            )

        index = self.decision_policy.select_model_index(
            eta,
            models,
        )

        return str(
            models[index]
        )

    def _draft_paragraph(
        self,
        *args,
        **kwargs,
    ) -> Optional[str]:
        """Delegate generation, then apply deterministic prose validation."""
        result = super()._draft_paragraph(
            *args,
            **kwargs,
        )

        if result is None:
            return None

        try:
            validated = validate_paragraph(
                result,
                min_words=self.min_paragraph_words,
                max_words=self.max_paragraph_words,
            )
        except WritingValidationError:
            return None

        return validated["text"]

    def _validate_section(
        self,
        section: Dict,
    ) -> bool:
        try:
            validate_section_structure(
                section,
                min_words=100,
            )
        except WritingValidationError:
            return False

        return super()._validate_section(
            section
        )

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
            if isinstance(
                section,
                dict,
            )
        ]
        self.last_decisions = []

        try:
            return super().run(
                section_topics,
                kb,
                existing_sections,
                errors,
            )
        finally:
            self._decision_sections = []
