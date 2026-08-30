#!/usr/bin/env python3
"""Convergence Detector - Determines when the pipeline has stabilized."""

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
        sections: List[Dict] = None
    ) -> Tuple[bool, Dict]:
        diagnostics = {
            "eta_variance": None, "invariant_violations": 0, "adjust_actions": len(recent_actions),
            "consecutive_clean_cycles": self.consecutive_convergence, "incomplete_sections": 0,
            "unstable_sections": 0, "converged": False,
        }
        
        # FIX #5 & #6: Only compute variance for ACTIVE section_topics
        eta_values = []
        for topic in section_topics:
            eta = writing_indicator.compute(topic, iteration_history)
            eta_values.append(eta)
        
        if len(eta_values) > 1:
            variance = statistics.variance(eta_values)
            diagnostics["eta_variance"] = variance
        else:
            variance = 0.0
        
        recent_failures = 0
        unstable_sections = 0
        
        # FIX #5: Only check audits for ACTIVE section_topics
        for section in section_topics:
            audits = iteration_history.audits.get(section, [])
            recent = audits[-self.m:] if len(audits) >= self.m else audits
            failures = sum(1 for audit in recent if not audit)
            recent_failures += failures
            
            if len(audits) < self.m or not all(audits[-self.m:]):
                unstable_sections += 1
                
        diagnostics["invariant_violations"] = recent_failures
        diagnostics["unstable_sections"] = unstable_sections
        
        incomplete_sections = 0
        if sections:
            for sec in sections:
                content = sec.get("content", "")
                if len(content.split()) < self.min_words_per_section:
                    incomplete_sections += 1
        diagnostics["incomplete_sections"] = incomplete_sections
        
        variance_ok = variance < self.epsilon
        no_violations = recent_failures == 0
        no_actions = len(recent_actions) == 0
        all_sections_stable = unstable_sections == 0
        all_sections_complete = incomplete_sections == 0
        
        is_converged = (variance_ok and no_violations and no_actions and all_sections_stable and all_sections_complete)
        
        if is_converged: self.consecutive_convergence += 1
        else: self.consecutive_convergence = 0
            
        diagnostics["consecutive_clean_cycles"] = self.consecutive_convergence
        diagnostics["converged"] = is_converged
        
        return is_converged, diagnostics
    
    def should_skip_write_phase(self, is_converged: bool, new_sources_found: bool) -> bool:
        if is_converged and not new_sources_found: return True
        return False
    
    def should_skip_extract_phase(self, unprocessed_sources: int) -> bool:
        return unprocessed_sources == 0
