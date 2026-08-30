#!/usr/bin/env python3
"""
OAA Loop.

Observes document-level anomalies and proposes structural corrections.

Supported actions:
- split_section
- merge_sections
- deduplicate
- expand_shorter
"""

import re
import sys
from typing import Dict, List, Optional


SUPPORTED_ACTIONS = {
    "split_section",
    "merge_sections",
    "deduplicate",
    "expand_shorter",
}


def calculate_similarity(
    text1: str,
    text2: str,
) -> float:
    """Calculate Jaccard similarity between two texts."""

    words1 = set(
        re.findall(
            r"\w+",
            str(text1).lower(),
        )
    )

    words2 = set(
        re.findall(
            r"\w+",
            str(text2).lower(),
        )
    )

    if not words1 or not words2:
        return 0.0

    intersection = words1.intersection(
        words2
    )

    union = words1.union(
        words2
    )

    if not union:
        return 0.0

    return (
        len(intersection)
        / len(union)
    )


class OAALoop:

    def __init__(
        self,
        config: Dict,
        section_splitter,
        section_merger,
    ):
        writing_config = config.get(
            "writing",
            {},
        )

        budget_config = config.get(
            "budget",
            {},
        )

        self.hysteresis_threshold = max(
            1,
            int(
                writing_config.get(
                    "hysteresis",
                    2,
                )
            ),
        )

        self.anomaly_counts: Dict[str, int] = {}

        self.section_splitter = (
            section_splitter
        )

        self.section_merger = (
            section_merger
        )

        self.max_calls = int(
            budget_config.get(
                "max_llm_calls_per_run",
                20,
            )
        )

        self.similarity_threshold = float(
            writing_config.get(
                "similarity_threshold",
                0.7,
            )
        )

        self.length_ratio_threshold = float(
            writing_config.get(
                "length_ratio_threshold",
                0.3,
            )
        )

    # ------------------------------------------------------------
    # Persistent hysteresis
    # ------------------------------------------------------------

    def load_persisted_state(
        self,
        iteration_history,
    ) -> None:
        persisted = (
            iteration_history.get_anomaly_counts()
        )

        self.anomaly_counts = dict(
            persisted
        )

    def save_persisted_state(
        self,
        iteration_history,
    ) -> None:
        iteration_history.set_anomaly_counts(
            self.anomaly_counts
        )

    # ------------------------------------------------------------
    # Observation
    # ------------------------------------------------------------

    def observe(
        self,
        sections: List[Dict],
    ) -> List[Dict]:

        anomalies = []

        if not isinstance(
            sections,
            list,
        ):
            return anomalies

        for index in range(
            len(sections) - 1
        ):
            s1 = sections[index]
            s2 = sections[index + 1]

            if not isinstance(s1, dict):
                continue

            if not isinstance(s2, dict):
                continue

            title1 = str(
                s1.get("title", "")
            )

            title2 = str(
                s2.get("title", "")
            )

            content1 = str(
                s1.get("content", "")
            )

            content2 = str(
                s2.get("content", "")
            )

            # ----------------------------------------------------
            # Repetition
            # ----------------------------------------------------

            overlap = calculate_similarity(
                content1,
                content2,
            )

            if overlap > self.similarity_threshold:
                anomalies.append(
                    {
                        "type": "repetition",
                        "sections": [
                            title1,
                            title2,
                        ],
                        "detail": (
                            "Jaccard similarity: "
                            f"{overlap:.2%}"
                        ),
                        "key": (
                            f"repetition:"
                            f"{title1}:"
                            f"{title2}"
                        ),
                    }
                )

            # ----------------------------------------------------
            # Transition
            # ----------------------------------------------------

            if not self._has_logical_transition(
                s1,
                s2,
            ):
                anomalies.append(
                    {
                        "type": "missing_transition",
                        "sections": [
                            title1,
                            title2,
                        ],
                        "detail": (
                            "No logical transition "
                            "detected"
                        ),
                        "key": (
                            f"transition:"
                            f"{title1}:"
                            f"{title2}"
                        ),
                    }
                )

            # ----------------------------------------------------
            # Length imbalance
            # ----------------------------------------------------

            len1 = len(
                content1.split()
            )

            len2 = len(
                content2.split()
            )

            if len1 > 0 and len2 > 0:
                ratio = (
                    min(len1, len2)
                    / max(len1, len2)
                )

                if (
                    ratio
                    < self.length_ratio_threshold
                ):
                    anomalies.append(
                        {
                            "type": "length_imbalance",
                            "sections": [
                                title1,
                                title2,
                            ],
                            "detail": (
                                f"Length ratio: "
                                f"{ratio:.2f}"
                            ),
                            "key": (
                                f"length:"
                                f"{title1}:"
                                f"{title2}"
                            ),
                        }
                    )

        return anomalies

    def _has_logical_transition(
        self,
        s1: Dict,
        s2: Dict,
    ) -> bool:
        """
        Determine whether two adjacent sections have at least
        some lexical/structural continuity.

        This remains deliberately conservative: it is an anomaly
        detector, not a proof of semantic correctness.
        """

        content1 = str(
            s1.get(
                "content",
                "",
            )
        )

        content2 = str(
            s2.get(
                "content",
                "",
            )
        )

        if not content1 or not content2:
            return False

        end_of_s1 = content1[
            -250:
        ].lower()

        start_of_s2 = content2[
            :250
        ].lower()

        stop_words = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "and",
            "or",
            "but",
            "with",
            "this",
            "that",
            "it",
            "its",
            "be",
            "has",
            "have",
            "had",
            "do",
            "does",
            "can",
            "may",
            "will",
            "shall",
            "would",
            "could",
            "should",
        }

        words_end = (
            set(
                re.findall(
                    r"\w+",
                    end_of_s1,
                )
            )
            - stop_words
        )

        words_start = (
            set(
                re.findall(
                    r"\w+",
                    start_of_s2,
                )
            )
            - stop_words
        )

        if words_end and words_start:
            shared = words_end.intersection(
                words_start
            )

            ratio = (
                len(shared)
                / min(
                    len(words_end),
                    len(words_start),
                )
            )

            if ratio > 0.15:
                return True

        transition_phrases = [
            "building on",
            "following",
            "next",
            "having established",
            "with this foundation",
            "as discussed",
            "continuing",
            "in the previous",
            "as shown above",
            "therefore",
            "consequently",
            "moreover",
            "furthermore",
            "in addition",
            "similarly",
            "by analogy",
            "extending",
            "generalizing",
            "applying",
            "using",
            "based on",
            "given",
        ]

        for phrase in transition_phrases:
            if phrase in start_of_s2:
                return True

        return False

    # ------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------

    def analyze(
        self,
        anomalies: List[Dict],
        iteration_history,
        sections: List[Dict],
        knowledge_base: Dict,
    ) -> List[Dict]:

        self.load_persisted_state(
            iteration_history
        )

        actionable = []

        seen_keys = set()

        for anomaly in anomalies:
            if not isinstance(anomaly, dict):
                continue

            key = anomaly.get(
                "key"
            )

            if not key:
                continue

            seen_keys.add(key)

            self.anomaly_counts[key] = (
                self.anomaly_counts.get(
                    key,
                    0,
                )
                + 1
            )

            iteration_history.record_anomaly(
                key
            )

            if (
                self.anomaly_counts[key]
                >= self.hysteresis_threshold
            ):
                actionable.append(
                    anomaly
                )

        # Reset disappeared anomalies.
        for key in list(
            self.anomaly_counts.keys()
        ):
            if key not in seen_keys:
                self.anomaly_counts[key] = 0

        # --------------------------------------------------------
        # Too-simple sections
        # --------------------------------------------------------

        if isinstance(
            sections,
            list,
        ):
            for section in sections:
                if not isinstance(
                    section,
                    dict,
                ):
                    continue

                if self.section_splitter.is_too_simple(
                    section,
                    knowledge_base,
                ):
                    title = str(
                        section.get(
                            "title",
                            "",
                        )
                    )

                    actionable.append(
                        {
                            "type": "too_simple",
                            "section": title,
                            "detail": (
                                "Section has "
                                f"{len(str(section.get('content', '')).split())}"
                                " words"
                            ),
                            "key": (
                                f"too_simple:{title}"
                            ),
                        }
                    )

        # --------------------------------------------------------
        # Merge candidates
        # --------------------------------------------------------

        merge_candidates = (
            self.section_merger.find_merge_candidates(
                sections
            )
        )

        for idx1, idx2, overlap in merge_candidates:

            if not self.section_merger.should_merge(
                sections,
                overlap,
            ):
                continue

            title1 = sections[
                idx1
            ].get(
                "title",
                "",
            )

            title2 = sections[
                idx2
            ].get(
                "title",
                "",
            )

            actionable.append(
                {
                    "type": "merge_candidate",
                    "sections": [
                        title1,
                        title2,
                    ],
                    "detail": (
                        f"Overlap: {overlap:.2f}"
                    ),
                    "key": (
                        f"merge:"
                        f"{title1}:"
                        f"{title2}"
                    ),
                    "indices": [
                        idx1,
                        idx2,
                    ],
                }
            )

        self.save_persisted_state(
            iteration_history
        )

        return actionable

    # ------------------------------------------------------------
    # Adjustment selection
    # ------------------------------------------------------------

    def adjust(
        self,
        actionable_anomalies: List[Dict],
    ) -> Optional[Dict]:

        if not actionable_anomalies:
            return None

        # Prefer directly executable actions.
        priority = {
            "too_simple": 0,
            "merge_candidate": 1,
            "repetition": 2,
            "length_imbalance": 3,
        }

        candidates = [
            anomaly
            for anomaly in actionable_anomalies
            if isinstance(
                anomaly,
                dict,
            )
            and anomaly.get("type")
            in priority
        ]

        if not candidates:
            return None

        candidates.sort(
            key=lambda anomaly: priority.get(
                anomaly.get("type"),
                999,
            )
        )

        anomaly = candidates[0]
        anomaly_type = anomaly.get(
            "type"
        )

        if anomaly_type == "too_simple":

            action = {
                "action": "split_section",
                "section": anomaly.get(
                    "section",
                    "",
                ),
                "reason": anomaly.get(
                    "detail",
                    "",
                ),
            }

        elif anomaly_type == "merge_candidate":

            action = {
                "action": "merge_sections",
                "sections": anomaly.get(
                    "sections",
                    [],
                ),
                "indices": anomaly.get(
                    "indices",
                    [],
                ),
                "reason": anomaly.get(
                    "detail",
                    "",
                ),
            }

        elif anomaly_type == "repetition":

            action = {
                "action": "deduplicate",
                "sections": anomaly.get(
                    "sections",
                    [],
                ),
                "reason": anomaly.get(
                    "detail",
                    "",
                ),
            }

        elif anomaly_type == "length_imbalance":

            action = {
                "action": "expand_shorter",
                "sections": anomaly.get(
                    "sections",
                    [],
                ),
                "reason": anomaly.get(
                    "detail",
                    "",
                ),
            }

        else:
            return None

        if action["action"] not in SUPPORTED_ACTIONS:
            print(
                "[OAA] Unsupported action "
                f"'{action['action']}'",
                file=sys.stderr,
            )
            return None

        return action

    # ------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------

    def execute_adjustment(
        self,
        adjustment: Dict,
        sections: List[Dict],
        provider,
        parser,
        iteration_history,
    ) -> List[Dict]:

        if not adjustment:
            return sections

        action = adjustment.get(
            "action"
        )

        if action not in SUPPORTED_ACTIONS:
            print(
                f"[OAA] Unsupported action "
                f"'{action}'.",
                file=sys.stderr,
            )
            return sections

        if provider.total_calls >= self.max_calls:
            print(
                "[OAA] Budget exhausted; "
                f"cannot execute '{action}'.",
                file=sys.stderr,
            )
            return sections

        # --------------------------------------------------------
        # Split
        # --------------------------------------------------------

        if action == "split_section":

            target_title = adjustment.get(
                "section",
                "",
            )

            target = next(
                (
                    section
                    for section in sections
                    if section.get("title")
                    == target_title
                ),
                None,
            )

            if target is None:
                return sections

            subsection_topics = (
                self.section_splitter.generate_subsection_topics(
                    target_title,
                    target.get(
                        "content",
                        "",
                    ),
                    provider,
                    parser,
                )
            )

            if not subsection_topics:
                return sections

            new_subsections = (
                self.section_splitter.split_section_safe(
                    target,
                    subsection_topics,
                )
            )

            if not new_subsections:
                return sections

            index = sections.index(
                target
            )

            sections[
                index : index + 1
            ] = new_subsections

            print(
                f"    [OAA] Split "
                f"'{target_title}' into "
                f"{len(new_subsections)} "
                "subsections",
                file=sys.stderr,
            )

            iteration_history.reset_anomaly(
                f"too_simple:{target_title}"
            )

        # --------------------------------------------------------
        # Merge
        # --------------------------------------------------------

        elif action == "merge_sections":

            indices = adjustment.get(
                "indices",
                [],
            )

            if not isinstance(
                indices,
                list,
            ):
                return sections

            if len(indices) != 2:
                return sections

            try:
                i1 = int(indices[0])
                i2 = int(indices[1])
            except (
                TypeError,
                ValueError,
            ):
                return sections

            if i1 > i2:
                i1, i2 = i2, i1

            if (
                i1 < 0
                or i2 >= len(sections)
                or i1 == i2
            ):
                return sections

            title1 = sections[i1].get(
                "title",
                "",
            )

            title2 = sections[i2].get(
                "title",
                "",
            )

            merged = (
                self.section_merger.merge_sections(
                    sections[i1],
                    sections[i2],
                )
            )

            sections.pop(i2)
            sections.pop(i1)

            sections.insert(
                i1,
                merged,
            )

            print(
                f"    [OAA] Merged "
                f"'{title1}' and "
                f"'{title2}'.",
                file=sys.stderr,
            )

            iteration_history.reset_anomaly(
                f"merge:{title1}:{title2}"
            )

        # --------------------------------------------------------
        # Deduplicate
        # --------------------------------------------------------

        elif action == "deduplicate":

            titles = adjustment.get(
                "sections",
                [],
            )

            if len(titles) != 2:
                return sections

            s1 = next(
                (
                    section
                    for section in sections
                    if section.get("title")
                    == titles[0]
                ),
                None,
            )

            s2 = next(
                (
                    section
                    for section in sections
                    if section.get("title")
                    == titles[1]
                ),
                None,
            )

            if s1 is None or s2 is None:
                return sections

            content1 = str(
                s1.get(
                    "content",
                    "",
                )
            )

            content2 = str(
                s2.get(
                    "content",
                    "",
                )
            )

            if len(content1) >= len(content2):
                s2["content"] = ""
                s2["status"] = "needs_rewrite"
                s2[
                    "deduplicate_from"
                ] = s1.get(
                    "title",
                    "",
                )

            else:
                s1["content"] = ""
                s1["status"] = "needs_rewrite"
                s1[
                    "deduplicate_from"
                ] = s2.get(
                    "title",
                    "",
                )

            print(
                "    [OAA] Deduplicated pair; "
                "shorter section marked "
                "for rewrite.",
                file=sys.stderr,
            )

        # --------------------------------------------------------
        # Expand shorter
        # --------------------------------------------------------

        elif action == "expand_shorter":

            titles = adjustment.get(
                "sections",
                [],
            )

            if len(titles) != 2:
                return sections

            s1 = next(
                (
                    section
                    for section in sections
                    if section.get("title")
                    == titles[0]
                ),
                None,
            )

            s2 = next(
                (
                    section
                    for section in sections
                    if section.get("title")
                    == titles[1]
                ),
                None,
            )

            if s1 is None or s2 is None:
                return sections

            len1 = len(
                str(
                    s1.get(
                        "content",
                        "",
                    )
                ).split()
            )

            len2 = len(
                str(
                    s2.get(
                        "content",
                        "",
                    )
                ).split()
            )

            if len1 < len2:

                s1["status"] = (
                    "needs_expansion"
                )

                s1[
                    "expansion_target"
                ] = s2.get(
                    "title",
                    "",
                )

            else:

                s2["status"] = (
                    "needs_expansion"
                )

                s2[
                    "expansion_target"
                ] = s1.get(
                    "title",
                    "",
                )

            print(
                "    [OAA] Shorter section "
                "marked for expansion.",
                file=sys.stderr,
            )

        return sections

    # ------------------------------------------------------------
    # Full OAA cycle
    # ------------------------------------------------------------

    def run(
        self,
        sections: List[Dict],
        iteration_history,
        knowledge_base: Dict,
    ) -> Optional[Dict]:

        anomalies = self.observe(
            sections
        )

        actionable = self.analyze(
            anomalies,
            iteration_history,
            sections,
            knowledge_base,
        )

        if not actionable:
            return None

        return self.adjust(
            actionable
        )
