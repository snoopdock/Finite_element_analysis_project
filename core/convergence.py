#!/usr/bin/env python3
"""
Convergence Detector - Determines when the pipeline has stabilized.

Convergence is based on observable document properties rather than
treating eta itself as a measure of document quality.
"""

import statistics
from typing import Dict, List, Tuple


class ConvergenceDetector:

    def __init__(
        self,
        config: Dict,
    ):
        convergence_config = config.get(
            "convergence",
            {},
        )

        self.m = int(
            convergence_config.get(
                "window",
                3,
            )
        )

        self.epsilon = float(
            convergence_config.get(
                "eta_variance_threshold",
                0.1,
            )
        )

        self.min_words_per_section = int(
            convergence_config.get(
                "min_words_per_section",
                150,
            )
        )

        self.minimum_reading_coverage = float(
            convergence_config.get(
                "minimum_reading_coverage_percent",
                80.0,
            )
        )

        self.consecutive_convergence = 0

    def check_convergence(
        self,
        iteration_history,
        writing_indicator,
        section_topics: List[str],
        recent_actions: List[str],
        sections: List[Dict] = None,
        reading_summary: Dict = None,
    ) -> Tuple[bool, Dict]:
        """
        Determine whether the document has reached a stable state.
        """

        sections = sections or []
        recent_actions = recent_actions or []

        diagnostics = {
            "eta_variance": None,
            "invariant_violations": 0,
            "adjust_actions": len(recent_actions),
            "consecutive_clean_cycles": (
                self.consecutive_convergence
            ),
            "incomplete_sections": 0,
            "unstable_sections": 0,
            "reading_coverage": 0.0,
            "converged": False,
            "reasons": [],
        }

        # ------------------------------------------------------------
        # 1. Eta variance
        # ------------------------------------------------------------

        eta_values = []

        for topic in section_topics:
            if not topic:
                continue

            eta = writing_indicator.compute(
                topic,
                iteration_history,
            )

            eta_values.append(
                float(eta)
            )

        if len(eta_values) > 1:
            variance = statistics.variance(
                eta_values
            )
        else:
            variance = 0.0

        diagnostics["eta_variance"] = variance

        variance_ok = (
            variance < self.epsilon
        )

        # ------------------------------------------------------------
        # 2. Recent audit failures / unstable sections
        # ------------------------------------------------------------

        recent_failures = 0
        unstable_sections = 0

        for topic in section_topics:
            if not topic:
                continue

            audits = iteration_history.audits.get(
                topic,
                [],
            )

            if not audits:
                unstable_sections += 1
                continue

            recent = audits[-self.m:]

            failures = sum(
                1
                for audit in recent
                if not bool(audit)
            )

            recent_failures += failures

            if (
                len(audits) < self.m
                or not all(
                    bool(audit)
                    for audit in recent
                )
            ):
                unstable_sections += 1

        diagnostics[
            "invariant_violations"
        ] = recent_failures

        diagnostics[
            "unstable_sections"
        ] = unstable_sections

        # ------------------------------------------------------------
        # 3. Section completeness
        # ------------------------------------------------------------

        incomplete_sections = 0

        for sec in sections:
            if not isinstance(sec, dict):
                incomplete_sections += 1
                continue

            content = sec.get(
                "content",
                "",
            )

            if not isinstance(content, str):
                content = str(content)

            status = sec.get(
                "status",
                "",
            )

            word_count = len(
                content.split()
            )

            if word_count < self.min_words_per_section:
                incomplete_sections += 1
                continue

            if status in {
                "needs_generation",
                "needs_rewrite",
                "needs_expansion",
                "incomplete",
            }:
                incomplete_sections += 1

        diagnostics[
            "incomplete_sections"
        ] = incomplete_sections

        # ------------------------------------------------------------
        # 4. Reading coverage
        # ------------------------------------------------------------

        if reading_summary is None:
            reading_coverage = 0.0
            diagnostics["reasons"].append(
                "reading_summary_missing"
            )
        else:
            reading_coverage = float(
                reading_summary.get(
                    "reading_coverage_percent",
                    0.0,
                )
            )

        diagnostics[
            "reading_coverage"
        ] = reading_coverage

        sufficient_reading = (
            reading_coverage
            >= self.minimum_reading_coverage
        )

        # ------------------------------------------------------------
        # 5. Final decision
        # ------------------------------------------------------------

        no_violations = (
            recent_failures == 0
        )

        no_actions = (
            len(recent_actions) == 0
        )

        all_sections_stable = (
            unstable_sections == 0
        )

        all_sections_complete = (
            incomplete_sections == 0
        )

        conditions = {
            "variance_ok": variance_ok,
            "no_violations": no_violations,
            "no_actions": no_actions,
            "all_sections_stable": all_sections_stable,
            "all_sections_complete": all_sections_complete,
            "sufficient_reading": sufficient_reading,
        }

        for name, passed in conditions.items():
            if not passed:
                diagnostics[
                    "reasons"
                ].append(name)

        is_converged = all(
            conditions.values()
        )

        if is_converged:
            self.consecutive_convergence += 1
        else:
            self.consecutive_convergence = 0

        diagnostics[
            "consecutive_clean_cycles"
        ] = self.consecutive_convergence

        diagnostics[
            "converged"
        ] = is_converged

        return (
            is_converged,
            diagnostics,
        )

    def should_skip_write_phase(
        self,
        is_converged: bool,
        new_sources_found: bool,
    ) -> bool:
        return bool(
            is_converged
            and not new_sources_found
        )

    def should_skip_extract_phase(
        self,
        unprocessed_sources: int,
    ) -> bool:
        return int(
            unprocessed_sources
        ) <= 0
