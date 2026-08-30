#!/usr/bin/env python3
"""
Convergence Detector - Determines when the pipeline has stabilized.
FIX #3: Separates scheduling priority (eta) from actual document quality convergence.
"""

import statistics
from typing import Dict, List, Tuple


class ConvergenceDetector:
    def __init__(self, config: Dict):
        self.m = config.get("convergence", {}).get("window", 3)
        self.epsilon = config.get("convergence", {}).get("eta_variance_threshold", 0.1)
        self.min_words_per_section = config.get("convergence", {}).get("min_words_per_section", 150)
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
        FIX #3: Convergence is now based on observable document properties,
        not just eta variance (which is a scheduling metric, not a quality metric).
        """
        diagnostics = {
            "eta_variance": None,
            "invariant_violations": 0,
            "adjust_actions": len(recent_actions),
            "consecutive_clean_cycles": self.consecutive_convergence,
            "incomplete_sections": 0,
            "unstable_sections": 0,
            "reading_coverage": 0.0,
            "converged": False,
        }

        # --- Scheduling metric (eta variance) ---
        # This measures scheduling stability, NOT document quality
        eta_values = []
        for topic in section_topics:
            eta = writing_indicator.compute(topic, iteration_history)
            eta_values.append(eta)

        if len(eta_values) > 1:
            variance = statistics.variance(eta_values)
            diagnostics["eta_variance"] = variance
        else:
            variance = 0.0

        # --- Document quality metrics (actual convergence) ---

        # 1. Check for invariant violations (failed audits)
        recent_failures = 0
        unstable_sections = 0
        for section in section_topics:
            audits = iteration_history.audits.get(section, [])
            recent = audits[-self.m:] if len(audits) >= self.m else audits
            failures = sum(1 for audit in recent if not audit)
            recent_failures += failures
            if len(audits) < self.m or not all(audits[-self.m:]):
                unstable_sections += 1

        diagnostics["invariant_violations"] = recent_failures
        diagnostics["unstable_sections"] = unstable_sections

        # 2. Check section completeness
        incomplete_sections = 0
        if sections:
            for sec in sections:
                content = sec.get("content", "")
                status = sec.get("status", "")
                if len(content.split()) < self.min_words_per_section:
                    incomplete_sections += 1
                elif status in ("needs_generation", "needs_rewrite", "needs_expansion"):
                    incomplete_sections += 1

        diagnostics["incomplete_sections"] = incomplete_sections

        # 3. Check reading coverage (FIX #3: New quality metric)
        reading_coverage = 0.0
        if reading_summary:
            reading_coverage = reading_summary.get("reading_coverage_percent", 0.0)
            diagnostics["reading_coverage"] = reading_coverage

        # --- Convergence decision ---
        # FIX #3: Convergence requires ALL of these observable properties:
        variance_ok = variance < self.epsilon
        no_violations = recent_failures == 0
        no_actions = len(recent_actions) == 0
        all_sections_stable = unstable_sections == 0
        all_sections_complete = incomplete_sections == 0
        sufficient_reading = reading_coverage >= 80.0  # At least 80% of sources read

        is_converged = (
            variance_ok and
            no_violations and
            no_actions and
            all_sections_stable and
            all_sections_complete and
            sufficient_reading
        )

        if is_converged:
            self.consecutive_convergence += 1
        else:
            self.consecutive_convergence = 0

        diagnostics["consecutive_clean_cycles"] = self.consecutive_convergence
        diagnostics["converged"] = is_converged

        return is_converged, diagnostics

    def should_skip_write_phase(self, is_converged: bool, new_sources_found: bool) -> bool:
        if is_converged and not new_sources_found:
            return True
        return False

    def should_skip_extract_phase(self, unprocessed_sources: int) -> bool:
        return unprocessed_sources == 0
