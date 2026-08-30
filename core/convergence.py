#!/usr/bin/env python3
"""Convergence detection based on document state and reading coverage."""

from __future__ import annotations

import statistics
from typing import Dict, List, Tuple

from core.section_identity import ensure_section_id


class ConvergenceDetector:
    def __init__(self, config: Dict):
        convergence_config = config.get("convergence", {})
        self.m = max(1, int(convergence_config.get("window", 3)))
        self.epsilon = float(convergence_config.get("eta_variance_threshold", 0.1))
        self.min_words_per_section = int(convergence_config.get("min_words_per_section", 150))
        self.minimum_reading_coverage = float(
            convergence_config.get("minimum_reading_coverage_percent", 80.0)
        )
        self.consecutive_convergence = 0

    @staticmethod
    def _section_for_topic(topic: str, sections: List[Dict]):
        topic_lower = str(topic).strip().lower()
        for section in sections:
            if not isinstance(section, dict):
                continue
            if str(section.get("title", "")).strip().lower() == topic_lower:
                ensure_section_id(section)
                return section
        return None

    def check_convergence(
        self,
        iteration_history,
        writing_indicator,
        section_topics: List[str],
        recent_actions: List[str],
        sections: List[Dict] = None,
        reading_summary: Dict = None,
    ) -> Tuple[bool, Dict]:
        sections = sections or []
        recent_actions = recent_actions or []

        diagnostics = {
            "eta_variance": None,
            "invariant_violations": 0,
            "adjust_actions": len(recent_actions),
            "consecutive_clean_cycles": self.consecutive_convergence,
            "incomplete_sections": 0,
            "unstable_sections": 0,
            "reading_coverage": 0.0,
            "converged": False,
            "reasons": [],
        }

        eta_values = []
        resolved_sections = []
        for topic in section_topics:
            if not topic:
                continue
            section = self._section_for_topic(topic, sections)
            target = section if section is not None else topic
            eta_values.append(float(writing_indicator.compute(target, iteration_history)))
            if section is not None:
                resolved_sections.append(section)

        variance = statistics.variance(eta_values) if len(eta_values) > 1 else 0.0
        diagnostics["eta_variance"] = variance
        variance_ok = variance < self.epsilon

        recent_failures = 0
        unstable_sections = 0
        for topic in section_topics:
            if not topic:
                continue
            section = self._section_for_topic(topic, sections)
            history_key = section.get("section_id") if section else topic
            audits = iteration_history.audits.get(history_key, [])

            if not audits:
                unstable_sections += 1
                continue

            recent = audits[-self.m:]
            recent_failures += sum(1 for audit in recent if not bool(audit))
            if len(audits) < self.m or not all(bool(audit) for audit in recent):
                unstable_sections += 1

        diagnostics["invariant_violations"] = recent_failures
        diagnostics["unstable_sections"] = unstable_sections

        incomplete_sections = 0
        for section in sections:
            if not isinstance(section, dict):
                incomplete_sections += 1
                continue

            content = section.get("content", "")
            content = content if isinstance(content, str) else str(content)
            status = section.get("status", "")

            if len(content.split()) < self.min_words_per_section:
                incomplete_sections += 1
                continue

            if status in {"needs_generation", "needs_rewrite", "needs_expansion", "incomplete"}:
                incomplete_sections += 1

        diagnostics["incomplete_sections"] = incomplete_sections

        if reading_summary is None:
            reading_coverage = 0.0
            diagnostics["reasons"].append("reading_summary_missing")
        else:
            reading_coverage = float(reading_summary.get("reading_coverage_percent", 0.0))

        diagnostics["reading_coverage"] = reading_coverage

        conditions = {
            "variance_ok": variance_ok,
            "no_violations": recent_failures == 0,
            "no_actions": len(recent_actions) == 0,
            "all_sections_stable": unstable_sections == 0,
            "all_sections_complete": incomplete_sections == 0,
            "sufficient_reading": reading_coverage >= self.minimum_reading_coverage,
        }

        for name, passed in conditions.items():
            if not passed:
                diagnostics["reasons"].append(name)

        is_converged = all(conditions.values())
        self.consecutive_convergence = self.consecutive_convergence + 1 if is_converged else 0
        diagnostics["consecutive_clean_cycles"] = self.consecutive_convergence
        diagnostics["converged"] = is_converged

        return is_converged, diagnostics

    def should_skip_write_phase(self, is_converged: bool, new_sources_found: bool) -> bool:
        return bool(is_converged and not new_sources_found)

    def should_skip_extract_phase(self, unprocessed_sources: int) -> bool:
        return int(unprocessed_sources) <= 0
