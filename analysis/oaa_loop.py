#!/usr/bin/env python3
"""Observation-Analysis-Adjustment loop for document structure."""

from __future__ import annotations

import re
import sys
from typing import Dict, List, Optional

from core.section_identity import ensure_section_id, get_section_id

SUPPORTED_ACTIONS = {
    "split_section",
    "merge_sections",
    "deduplicate",
    "expand_shorter",
}


def calculate_similarity(text1: str, text2: str) -> float:
    words1 = set(re.findall(r"\w+", str(text1).lower()))
    words2 = set(re.findall(r"\w+", str(text2).lower()))
    if not words1 or not words2:
        return 0.0
    return len(words1 & words2) / len(words1 | words2)


def _section_identity(section: Dict) -> str:
    section_id = get_section_id(section)
    return section_id if section_id else str(section.get("title", ""))


class OAALoop:
    def __init__(self, config: Dict, section_splitter, section_merger):
        writing = config.get("writing", {})
        budget = config.get("budget", {})
        self.hysteresis_threshold = max(1, int(writing.get("hysteresis", 2)))
        self.section_splitter = section_splitter
        self.section_merger = section_merger
        self.max_calls = int(budget.get("max_llm_calls_per_run", 20))
        self.similarity_threshold = float(writing.get("similarity_threshold", 0.7))
        self.length_ratio_threshold = float(writing.get("length_ratio_threshold", 0.3))
        self.anomaly_counts: Dict[str, int] = {}

    def load_persisted_state(self, iteration_history) -> None:
        self.anomaly_counts = iteration_history.get_anomaly_counts()

    def save_persisted_state(self, iteration_history) -> None:
        iteration_history.set_anomaly_counts(self.anomaly_counts)

    def _pair_key(self, kind: str, section1: Dict, section2: Dict) -> str:
        return f"{kind}:{_section_identity(section1)}:{_section_identity(section2)}"

    def observe(self, sections: List[Dict]) -> List[Dict]:
        anomalies = []
        if not isinstance(sections, list):
            return anomalies

        for index in range(len(sections) - 1):
            s1, s2 = sections[index], sections[index + 1]
            if not isinstance(s1, dict) or not isinstance(s2, dict):
                continue

            ensure_section_id(s1)
            ensure_section_id(s2)
            title1 = str(s1.get("title", ""))
            title2 = str(s2.get("title", ""))
            content1 = str(s1.get("content", ""))
            content2 = str(s2.get("content", ""))

            overlap = calculate_similarity(content1, content2)
            if overlap > self.similarity_threshold:
                anomalies.append({
                    "type": "repetition",
                    "section_ids": [s1["section_id"], s2["section_id"]],
                    "sections": [title1, title2],
                    "detail": f"Jaccard similarity: {overlap:.2%}",
                    "key": self._pair_key("repetition", s1, s2),
                })

            if not self._has_logical_transition(s1, s2):
                anomalies.append({
                    "type": "missing_transition",
                    "section_ids": [s1["section_id"], s2["section_id"]],
                    "sections": [title1, title2],
                    "detail": "No logical transition detected",
                    "key": self._pair_key("transition", s1, s2),
                })

            len1, len2 = len(content1.split()), len(content2.split())
            if len1 > 0 and len2 > 0:
                ratio = min(len1, len2) / max(len1, len2)
                if ratio < self.length_ratio_threshold:
                    anomalies.append({
                        "type": "length_imbalance",
                        "section_ids": [s1["section_id"], s2["section_id"]],
                        "sections": [title1, title2],
                        "detail": f"Length ratio: {ratio:.2f}",
                        "key": self._pair_key("length", s1, s2),
                    })

        return anomalies

    def _has_logical_transition(self, s1: Dict, s2: Dict) -> bool:
        content1 = str(s1.get("content", ""))
        content2 = str(s2.get("content", ""))
        if not content1 or not content2:
            return False

        end_words = set(re.findall(r"\w+", content1[-250:].lower()))
        start_words = set(re.findall(r"\w+", content2[:250].lower()))
        stop = {
            "the", "a", "an", "is", "are", "was", "were", "in", "on", "at",
            "to", "for", "of", "and", "or", "but", "with", "this", "that", "it",
            "its", "be", "has", "have", "had", "do", "does", "can", "may", "will",
            "shall", "would", "could", "should",
        }
        end_words -= stop
        start_words -= stop

        if end_words and start_words:
            ratio = len(end_words & start_words) / min(len(end_words), len(start_words))
            if ratio > 0.15:
                return True

        transition_phrases = {
            "building on", "following", "next", "having established",
            "with this foundation", "as discussed", "continuing",
            "in the previous", "as shown above", "therefore", "consequently",
            "moreover", "furthermore", "in addition", "similarly", "by analogy",
            "extending", "generalizing", "applying", "using", "based on", "given",
        }
        start_lower = content2[:250].lower()
        return any(phrase in start_lower for phrase in transition_phrases)

    def analyze(self, anomalies: List[Dict], iteration_history, sections: List[Dict], knowledge_base: Dict) -> List[Dict]:
        self.load_persisted_state(iteration_history)
        actionable = []
        seen_keys = set()

        for anomaly in anomalies:
            if not isinstance(anomaly, dict):
                continue
            key = anomaly.get("key")
            if not key:
                continue
            seen_keys.add(key)
            self.anomaly_counts[key] = self.anomaly_counts.get(key, 0) + 1
            iteration_history.record_anomaly(key)
            if self.anomaly_counts[key] >= self.hysteresis_threshold:
                actionable.append(anomaly)

        for key in list(self.anomaly_counts):
            if key not in seen_keys:
                self.anomaly_counts[key] = 0
                iteration_history.reset_hysteresis(key)

        for section in sections if isinstance(sections, list) else []:
            if not isinstance(section, dict):
                continue
            ensure_section_id(section)
            if self.section_splitter.is_too_simple(section, knowledge_base):
                sid = section["section_id"]
                actionable.append({
                    "type": "too_simple",
                    "section_id": sid,
                    "section": section.get("title", ""),
                    "detail": f"Section has {len(str(section.get('content', '')).split())} words",
                    "key": f"too_simple:{sid}",
                })

        for idx1, idx2, overlap in self.section_merger.find_merge_candidates(sections):
            if not self.section_merger.should_merge(sections, overlap):
                continue
            s1, s2 = sections[idx1], sections[idx2]
            ensure_section_id(s1)
            ensure_section_id(s2)
            actionable.append({
                "type": "merge_candidate",
                "section_ids": [s1["section_id"], s2["section_id"]],
                "sections": [s1.get("title", ""), s2.get("title", "")],
                "indices": [idx1, idx2],
                "detail": f"Overlap: {overlap:.2f}",
                "key": self._pair_key("merge", s1, s2),
            })

        self.save_persisted_state(iteration_history)
        return actionable

    def adjust(self, actionable_anomalies: List[Dict]) -> Optional[Dict]:
        if not actionable_anomalies:
            return None

        priority = {
            "too_simple": 0,
            "merge_candidate": 1,
            "repetition": 2,
            "length_imbalance": 3,
        }
        candidates = [
            anomaly for anomaly in actionable_anomalies
            if isinstance(anomaly, dict) and anomaly.get("type") in priority
        ]
        if not candidates:
            return None

        candidates.sort(key=lambda anomaly: priority[anomaly["type"]])
        anomaly = candidates[0]
        kind = anomaly["type"]

        if kind == "too_simple":
            return {
                "action": "split_section",
                "section_id": anomaly.get("section_id"),
                "section": anomaly.get("section", ""),
                "reason": anomaly.get("detail", ""),
            }
        if kind == "merge_candidate":
            return {
                "action": "merge_sections",
                "section_ids": anomaly.get("section_ids", []),
                "sections": anomaly.get("sections", []),
                "indices": anomaly.get("indices", []),
                "reason": anomaly.get("detail", ""),
            }
        if kind == "repetition":
            return {
                "action": "deduplicate",
                "section_ids": anomaly.get("section_ids", []),
                "sections": anomaly.get("sections", []),
                "reason": anomaly.get("detail", ""),
            }
        if kind == "length_imbalance":
            return {
                "action": "expand_shorter",
                "section_ids": anomaly.get("section_ids", []),
                "sections": anomaly.get("sections", []),
                "reason": anomaly.get("detail", ""),
            }
        return None

    @staticmethod
    def _find_by_id(sections: List[Dict], section_id: str) -> Optional[Dict]:
        if not section_id:
            return None
        for section in sections:
            if isinstance(section, dict) and get_section_id(section) == section_id:
                return section
        return None

    @staticmethod
    def _reset_adjustment_state(iteration_history, key: str) -> None:
        reset_state = getattr(
            iteration_history,
            "reset_anomaly_state",
            None,
        )
        if callable(reset_state):
            reset_state(key)
        else:
            iteration_history.reset_anomaly(key)

    def execute_adjustment(self, adjustment: Dict, sections: List[Dict], provider, parser, iteration_history) -> List[Dict]:
        if not adjustment:
            return sections

        action = adjustment.get("action")
        if action not in SUPPORTED_ACTIONS:
            return sections

        if provider.budget_exhausted():
            print(
                f"[OAA] Budget exhausted; cannot execute '{action}'.",
                file=sys.stderr,
            )
            return sections

        if action == "split_section":
            target = self._find_by_id(
                sections,
                adjustment.get("section_id"),
            )

            if target is None and adjustment.get("section"):
                target = next(
                    (
                        s for s in sections
                        if s.get("title") == adjustment["section"]
                    ),
                    None,
                )

            if target is None:
                return sections

            target_id = ensure_section_id(target)
            topics = self.section_splitter.generate_subsection_topics(
                target.get("title", ""),
                target.get("content", ""),
                provider,
                parser,
            )

            if not topics:
                return sections

            children = self.section_splitter.split_section_safe(
                target,
                topics,
            )

            if not children:
                return sections

            index = sections.index(target)
            sections[index:index + 1] = children
            self._reset_adjustment_state(
                iteration_history,
                f"too_simple:{target_id}",
            )
            self.anomaly_counts[f"too_simple:{target_id}"] = 0
            return sections

        if action == "merge_sections":
            ids = adjustment.get("section_ids", [])
            if len(ids) == 2:
                s1 = self._find_by_id(sections, ids[0])
                s2 = self._find_by_id(sections, ids[1])
            else:
                s1 = s2 = None

            if s1 is None or s2 is None:
                indices = adjustment.get("indices", [])
                if len(indices) != 2:
                    return sections
                try:
                    i1, i2 = sorted(
                        (int(indices[0]), int(indices[1]))
                    )
                    if (
                        i1 < 0
                        or i2 >= len(sections)
                        or i1 == i2
                    ):
                        return sections
                    s1, s2 = sections[i1], sections[i2]
                except (TypeError, ValueError):
                    return sections

            id1 = ensure_section_id(s1)
            id2 = ensure_section_id(s2)
            original_index = min(
                sections.index(s1),
                sections.index(s2),
            )

            merged = self.section_merger.merge_sections(
                s1,
                s2,
            )

            merged["parent_section_ids"] = [
                id1,
                id2,
            ]

            sections[:] = [
                section
                for section in sections
                if section is not s1
                and section is not s2
            ]

            sections.insert(
                min(original_index, len(sections)),
                merged,
            )

            self._reset_adjustment_state(
                iteration_history,
                f"merge:{id1}:{id2}",
            )
            self.anomaly_counts[f"merge:{id1}:{id2}"] = 0
            return sections

        if action == "deduplicate":
            ids = adjustment.get("section_ids", [])
            if len(ids) != 2:
                return sections

            s1 = self._find_by_id(sections, ids[0])
            s2 = self._find_by_id(sections, ids[1])

            if s1 is None or s2 is None:
                return sections

            c1 = str(s1.get("content", ""))
            c2 = str(s2.get("content", ""))

            if len(c1) >= len(c2):
                s2["content"] = ""
                s2["status"] = "needs_rewrite"
                s2["deduplicate_from_id"] = ensure_section_id(s1)
            else:
                s1["content"] = ""
                s1["status"] = "needs_rewrite"
                s1["deduplicate_from_id"] = ensure_section_id(s2)

            key = self._pair_key(
                "repetition",
                s1,
                s2,
            )
            self._reset_adjustment_state(
                iteration_history,
                key,
            )
            self.anomaly_counts[key] = 0
            return sections

        if action == "expand_shorter":
            ids = adjustment.get("section_ids", [])
            if len(ids) != 2:
                return sections

            s1 = self._find_by_id(sections, ids[0])
            s2 = self._find_by_id(sections, ids[1])

            if s1 is None or s2 is None:
                return sections

            n1 = len(
                str(
                    s1.get(
                        "content",
                        "",
                    )
                ).split()
            )

            n2 = len(
                str(
                    s2.get(
                        "content",
                        "",
                    )
                ).split()
            )

            if n1 < n2:
                s1["status"] = "needs_expansion"
                s1["expansion_target_id"] = ensure_section_id(s2)
            else:
                s2["status"] = "needs_expansion"
                s2["expansion_target_id"] = ensure_section_id(s1)

            key = self._pair_key(
                "length",
                s1,
                s2,
            )
            self._reset_adjustment_state(
                iteration_history,
                key,
            )
            self.anomaly_counts[key] = 0
            return sections

        return sections

    def run(self, sections: List[Dict], iteration_history, knowledge_base: Dict) -> Optional[Dict]:
        anomalies = self.observe(sections)
        actionable = self.analyze(
            anomalies,
            iteration_history,
            sections,
            knowledge_base,
        )
        return self.adjust(actionable)
