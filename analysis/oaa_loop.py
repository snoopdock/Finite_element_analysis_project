#!/usr/bin/env python3
"""OAA Loop with section splitting and merging execution."""

import sys
from typing import Any, Dict, List, Optional, Tuple


class OAALoop:
    def __init__(self, config: Dict, section_splitter, section_merger):
        self.hysteresis_threshold = config.get("writing", {}).get("hysteresis", 2)
        self.anomaly_counts: Dict[str, int] = {}
        self.section_splitter = section_splitter
        self.section_merger = section_merger
        self.max_calls = config.get("budget", {}).get("max_llm_calls_per_run", 20)
    
    def observe(self, sections: List[Dict]) -> List[Dict]:
        anomalies = []
        for i in range(len(sections) - 1):
            s1 = sections[i]
            s2 = sections[i + 1]
            
            overlap = self._check_concept_overlap(s1, s2)
            if overlap:
                anomalies.append({
                    "type": "repetition",
                    "sections": [s1.get("title", ""), s2.get("title", "")],
                    "detail": overlap,
                    "key": f"repetition:{s1.get('title', '')}:{s2.get('title', '')}",
                })
            
            if not self._has_transition(s1, s2):
                anomalies.append({
                    "type": "missing_transition",
                    "sections": [s1.get("title", ""), s2.get("title", "")],
                    "detail": "No logical transition",
                    "key": f"transition:{s1.get('title', '')}:{s2.get('title', '')}",
                })
            
            len1 = len(s1.get("content", "").split())
            len2 = len(s2.get("content", "").split())
            if len1 > 0 and len2 > 0:
                ratio = min(len1, len2) / max(len1, len2)
                if ratio < 0.3:
                    anomalies.append({
                        "type": "length_imbalance",
                        "sections": [s1.get("title", ""), s2.get("title", "")],
                        "detail": f"Length ratio: {ratio:.2f}",
                        "key": f"length:{s1.get('title', '')}:{s2.get('title', '')}",
                    })
        return anomalies
    
    def analyze(self, anomalies: List[Dict], iteration_history, sections: List[Dict], knowledge_base: Dict) -> List[Dict]:
        actionable = []
        
        for anomaly in anomalies:
            key = anomaly["key"]
            self.anomaly_counts[key] = self.anomaly_counts.get(key, 0) + 1
            count = self.anomaly_counts[key]
            iteration_history.record_anomaly(key)
            if count >= self.hysteresis_threshold:
                actionable.append(anomaly)
        
        seen_keys = {a["key"] for a in anomalies}
        for key in list(self.anomaly_counts.keys()):
            if key not in seen_keys:
                self.anomaly_counts[key] = 0
        
        # Check for too-simple sections
        for section in sections:
            if self.section_splitter.is_too_simple(section, knowledge_base):
                actionable.append({
                    "type": "too_simple",
                    "section": section.get("title", ""),
                    "detail": f"Section has {len(section.get('content', '').split())} words",
                    "key": f"too_simple:{section.get('title', '')}",
                })
        
        # Check for merge candidates
        merge_candidates = self.section_merger.find_merge_candidates(sections)
        for idx1, idx2, overlap in merge_candidates:
            if self.section_merger.should_merge(sections, overlap):
                actionable.append({
                    "type": "merge_candidate",
                    "sections": [sections[idx1].get("title", ""), sections[idx2].get("title", "")],
                    "detail": f"Overlap: {overlap:.2f}",
                    "key": f"merge:{sections[idx1].get('title', '')}:{sections[idx2].get('title', '')}",
                    "indices": [idx1, idx2],
                })
        
        return actionable
    
    def adjust(self, actionable_anomalies: List[Dict]) -> Optional[Dict]:
        if not actionable_anomalies:
            return None
        anomaly = actionable_anomalies[0]
        
        if anomaly["type"] == "too_simple":
            return {"action": "split_section", "section": anomaly["section"], "reason": anomaly["detail"]}
        elif anomaly["type"] == "merge_candidate":
            return {"action": "merge_sections", "sections": anomaly["sections"], "indices": anomaly.get("indices"), "reason": anomaly["detail"]}
        elif anomaly["type"] == "repetition":
            return {"action": "deduplicate", "sections": anomaly["sections"], "reason": anomaly["detail"]}
        elif anomaly["type"] == "length_imbalance":
            return {"action": "expand_shorter", "sections": anomaly["sections"], "reason": anomaly["detail"]}
        return None
    
    def execute_adjustment(self, adjustment: Dict, sections: List[Dict], provider, parser, iteration_history) -> List[Dict]:
        """FIX #3: Actually execute split/merge adjustments."""
        if not adjustment:
            return sections
        
        action = adjustment.get("action")
        
        if provider.total_calls >= self.max_calls:
            print(f"    [OAA] Skipping adjustment '{action}': Budget exhausted ({provider.total_calls}/{self.max_calls} calls)", file=sys.stderr)
            return sections

        if action == "split_section":
            target_title = adjustment.get("section", "")
            target = next((s for s in sections if s.get("title") == target_title), None)
            if target:
                subsection_topics = self.section_splitter.generate_subsection_topics(
                    target_title, target.get("content", ""), provider, parser
                )
                if subsection_topics:
                    new_subsections = self.section_splitter.split_section(target, subsection_topics)
                    # Replace the original section with subsections
                    idx = sections.index(target)
                    sections[idx:idx+1] = new_subsections
                    print(f"    [OAA] Split '{target_title}' into {len(new_subsections)} subsections", file=sys.stderr)
                    # Clear the anomaly
                    iteration_history.reset_anomaly(f"too_simple:{target_title}")
        
        elif action == "merge_sections":
            indices = adjustment.get("indices", [])
            if len(indices) == 2 and indices[0] < len(sections) and indices[1] < len(sections):
                title1 = sections[indices[0]].get('title', '')
                title2 = sections[indices[1]].get('title', '')
                merged = self.section_merger.merge_sections(sections[indices[0]], sections[indices[1]])
                # Remove both, insert merged
                sections.pop(indices[1])
                sections.pop(indices[0])
                sections.insert(indices[0], merged)
                print(f"    [OAA] Merged 2 sections into '{merged.get('title', '')}'", file=sys.stderr)
                # Clear the anomaly
                iteration_history.reset_anomaly(f"merge:{title1}:{title2}")
        
        return sections
    
    def _check_concept_overlap(self, s1: Dict, s2: Dict) -> Optional[str]:
        content1 = s1.get("content", "").lower()
        content2 = s2.get("content", "").lower()
        words1 = set(content1.split())
        words2 = set(content2.split())
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "in", "on",
                      "at", "to", "for", "of", "and", "or", "but", "with", "this",
                      "that", "it", "its", "be", "has", "have", "had", "do", "does"}
        words1 -= stop_words
        words2 -= stop_words
        if not words1 or not words2:
            return None
        overlap = words1 & words2
        overlap_ratio = len(overlap) / min(len(words1), len(words2)) if min(len(words1), len(words2)) > 0 else 0
        if overlap_ratio > 0.7:
            return f"Word overlap: {overlap_ratio:.0%}"
        return None
    
    def _has_transition(self, s1: Dict, s2: Dict) -> bool:
        """FIX #4: Return False on fallback instead of True."""
        content2 = s2.get("content", "").lower()
        transition_indicators = [
            "building on", "following", "next", "having established",
            "with this foundation", "as discussed", "continuing",
            "in the previous", "as shown above", "therefore",
        ]
        first_200_chars = content2[:200]
        for indicator in transition_indicators:
            if indicator in first_200_chars:
                return True
        return False  # FIXED: was returning True
    
    def run(self, sections: List[Dict], iteration_history, knowledge_base: Dict) -> Optional[Dict]:
        anomalies = self.observe(sections)
        if not anomalies and not sections:
            return None
        actionable = self.analyze(anomalies, iteration_history, sections, knowledge_base)
        if not actionable:
            return None
        return self.adjust(actionable)
