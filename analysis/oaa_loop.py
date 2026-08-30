#!/usr/bin/env python3
"""
OAA Loop with section splitting and merging execution.
Fixes: persistent hysteresis, unified similarity, implemented actions, better transitions.
"""

import sys
import re
from typing import Any, Dict, List, Optional, Tuple


# FIX #7: Define all supported actions explicitly
SUPPORTED_ACTIONS = {
    "split_section",
    "merge_sections",
    "deduplicate",
    "expand_shorter",
}


def calculate_similarity(text1: str, text2: str) -> float:
    """
    FIX #5: Unified similarity metric using Jaccard similarity.
    Used consistently across the entire pipeline.
    """
    words1 = set(re.findall(r'\w+', text1.lower()))
    words2 = set(re.findall(r'\w+', text2.lower()))
    if not words1 or not words2:
        return 0.0
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    return len(intersection) / len(union)


class OAALoop:
    def __init__(self, config: Dict, section_splitter, section_merger):
        self.hysteresis_threshold = config.get("writing", {}).get("hysteresis", 2)
        self.anomaly_counts: Dict[str, int] = {}
        self.section_splitter = section_splitter
        self.section_merger = section_merger
        self.max_calls = config.get("budget", {}).get("max_llm_calls_per_run", 20)
        self.similarity_threshold = config.get("writing", {}).get("similarity_threshold", 0.7)

    def load_persisted_state(self, iteration_history) -> None:
        """FIX #8: Load persisted anomaly counts from iteration history."""
        persisted = iteration_history.get_anomaly_counts()
        if persisted:
            self.anomaly_counts = persisted

    def save_persisted_state(self, iteration_history) -> None:
        """FIX #8: Save anomaly counts to iteration history for persistence."""
        iteration_history.set_anomaly_counts(self.anomaly_counts)

    def observe(self, sections: List[Dict]) -> List[Dict]:
        anomalies = []
        for i in range(len(sections) - 1):
            s1 = sections[i]
            s2 = sections[i + 1]

            # FIX #5: Use unified Jaccard similarity
            overlap = calculate_similarity(
                s1.get("content", ""),
                s2.get("content", "")
            )
            if overlap > self.similarity_threshold:
                anomalies.append({
                    "type": "repetition",
                    "sections": [s1.get("title", ""), s2.get("title", "")],
                    "detail": f"Jaccard similarity: {overlap:.2%}",
                    "key": f"repetition:{s1.get('title', '')}:{s2.get('title', '')}",
                })

            # FIX #4: Improved transition detection using semantic cues
            if not self._has_logical_transition(s1, s2):
                anomalies.append({
                    "type": "missing_transition",
                    "sections": [s1.get("title", ""), s2.get("title", "")],
                    "detail": "No logical transition detected",
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

    def _has_logical_transition(self, s1: Dict, s2: Dict) -> bool:
        """
        FIX #4: Improved transition detection.
        Instead of checking for exact phrases, checks for semantic continuity
        by looking for shared concepts between the end of s1 and beginning of s2.
        """
        content1 = s1.get("content", "")
        content2 = s2.get("content", "")

        if not content1 or not content2:
            return False

        # Get the last 200 chars of s1 and first 200 chars of s2
        end_of_s1 = content1[-200:].lower()
        start_of_s2 = content2[:200].lower()

        # Check for shared technical terms (excluding common stopwords)
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "in", "on",
                      "at", "to", "for", "of", "and", "or", "but", "with", "this",
                      "that", "it", "its", "be", "has", "have", "had", "do", "does",
                      "can", "may", "will", "shall", "would", "could", "should"}

        words_end = set(re.findall(r'\w+', end_of_s1)) - stop_words
        words_start = set(re.findall(r'\w+', start_of_s2)) - stop_words

        # If there's significant vocabulary overlap, consider it a valid transition
        if words_end and words_start:
            overlap = len(words_end.intersection(words_start)) / min(len(words_end), len(words_start))
            if overlap > 0.15:  # At least 15% shared technical vocabulary
                return True

        # Also check for explicit transition phrases (but don't rely solely on them)
        transition_phrases = [
            "building on", "following", "next", "having established",
            "with this foundation", "as discussed", "continuing",
            "in the previous", "as shown above", "therefore",
            "consequently", "moreover", "furthermore", "in addition",
            "similarly", "by analogy", "extending", "generalizing",
            "applying", "using", "based on", "given",
        ]
        for phrase in transition_phrases:
            if phrase in start_of_s2:
                return True

        return False

    def analyze(self, anomalies: List[Dict], iteration_history, sections: List[Dict], knowledge_base: Dict) -> List[Dict]:
        actionable = []

        # FIX #8: Load persisted anomaly counts
        self.load_persisted_state(iteration_history)

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

        # FIX #8: Save anomaly counts for persistence
        self.save_persisted_state(iteration_history)

        return actionable

    def adjust(self, actionable_anomalies: List[Dict]) -> Optional[Dict]:
        if not actionable_anomalies:
            return None
        anomaly = actionable_anomalies[0]

        if anomaly["type"] == "too_simple":
            action = {"action": "split_section", "section": anomaly["section"], "reason": anomaly["detail"]}
        elif anomaly["type"] == "merge_candidate":
            action = {"action": "merge_sections", "sections": anomaly["sections"], "indices": anomaly.get("indices"), "reason": anomaly["detail"]}
        elif anomaly["type"] == "repetition":
            action = {"action": "deduplicate", "sections": anomaly["sections"], "reason": anomaly["detail"]}
        elif anomaly["type"] == "length_imbalance":
            action = {"action": "expand_shorter", "sections": anomaly["sections"], "reason": anomaly["detail"]}
        else:
            action = None

        # FIX #7: Verify the action is supported before returning it
        if action and action["action"] not in SUPPORTED_ACTIONS:
            print(f"  [OAA] Warning: Unsupported action '{action['action']}' detected. Skipping.", file=sys.stderr)
            return None

        return action

    def execute_adjustment(self, adjustment: Dict, sections: List[Dict], provider, parser, iteration_history) -> List[Dict]:
        """Execute split/merge/deduplicate/expand adjustments."""
        if not adjustment:
            return sections

        action = adjustment.get("action")

        # FIX #7: Verify action is supported
        if action not in SUPPORTED_ACTIONS:
            print(f"  [OAA] Error: Unsupported action '{action}'. Cannot execute.", file=sys.stderr)
            return sections

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
                    # FIX #6: Create subsections with explicit state tracking
                    new_subsections = self.section_splitter.split_section_safe(target, subsection_topics)
                    idx = sections.index(target)
                    sections[idx:idx+1] = new_subsections
                    print(f"    [OAA] Split '{target_title}' into {len(new_subsections)} subsections", file=sys.stderr)
                    iteration_history.reset_anomaly(f"too_simple:{target_title}")

        elif action == "merge_sections":
            indices = adjustment.get("indices", [])
            if len(indices) == 2 and indices[0] < len(sections) and indices[1] < len(sections):
                title1 = sections[indices[0]].get('title', '')
                title2 = sections[indices[1]].get('title', '')
                merged = self.section_merger.merge_sections(sections[indices[0]], sections[indices[1]])
                sections.pop(indices[1])
                sections.pop(indices[0])
                sections.insert(indices[0], merged)
                print(f"    [OAA] Merged 2 sections into '{merged.get('title', '')}'", file=sys.stderr)
                iteration_history.reset_anomaly(f"merge:{title1}:{title2}")

        elif action == "deduplicate":
            # FIX #7: Implement deduplicate action
            section_titles = adjustment.get("sections", [])
            if len(section_titles) == 2:
                s1 = next((s for s in sections if s.get("title") == section_titles[0]), None)
                s2 = next((s for s in sections if s.get("title") == section_titles[1]), None)
                if s1 and s2:
                    # Keep the longer section, mark the shorter for rewrite
                    if len(s1.get("content", "")) >= len(s2.get("content", "")):
                        s2["content"] = ""
                        s2["status"] = "needs_rewrite"
                        s2["deduplicate_from"] = s1.get("title", "")
                    else:
                        s1["content"] = ""
                        s1["status"] = "needs_rewrite"
                        s1["deduplicate_from"] = s2.get("title", "")
                    print(f"    [OAA] Deduplicated: marked shorter section for rewrite", file=sys.stderr)

        elif action == "expand_shorter":
            # FIX #7: Implement expand_shorter action
            section_titles = adjustment.get("sections", [])
            if len(section_titles) == 2:
                s1 = next((s for s in sections if s.get("title") == section_titles[0]), None)
                s2 = next((s for s in sections if s.get("title") == section_titles[1]), None)
                if s1 and s2:
                    # Mark the shorter section for expansion
                    if len(s1.get("content", "")) < len(s2.get("content", "")):
                        s1["status"] = "needs_expansion"
                        s1["expansion_target"] = section_titles[1]
                    else:
                        s2["status"] = "needs_expansion"
                        s2["expansion_target"] = section_titles[0]
                    print(f"    [OAA] Marked shorter section for expansion", file=sys.stderr)

        return sections

    def run(self, sections: List[Dict], iteration_history, knowledge_base: Dict) -> Optional[Dict]:
        anomalies = self.observe(sections)
        if not anomalies and not sections:
            return None
        actionable = self.analyze(anomalies, iteration_history, sections, knowledge_base)
        if not actionable:
            return None
        return self.adjust(actionable)
