#!/usr/bin/env python3
"""Section Merger - Merges adjacent sections that are semantically similar."""

import re
from typing import Dict, List, Tuple

from core.section_identity import ensure_section_id, make_merged_section


class SectionMerger:
    def __init__(self, config: Dict):
        self.overlap_threshold = config.get("merging", {}).get("overlap_threshold", 0.6)
        self.min_section_count = config.get("merging", {}).get("min_section_count", 3)

    def find_merge_candidates(self, sections: List[Dict]) -> List[Tuple[int, int, float]]:
        candidates = []
        for i in range(len(sections) - 1):
            sec1, sec2 = sections[i], sections[i + 1]
            overlap = self._calculate_overlap(sec1, sec2)
            if overlap >= self.overlap_threshold:
                candidates.append((i, i + 1, overlap))
        candidates.sort(key=lambda x: x[2], reverse=True)
        return candidates

    def merge_sections(self, section1: Dict, section2: Dict) -> Dict:
        ensure_section_id(section1)
        ensure_section_id(section2)

        title1 = section1.get("title", "")
        title2 = section2.get("title", "")
        merged_title = f"{title1} (merged with {title2})"

        content1 = section1.get("content", "")
        content2 = section2.get("content", "")
        merged_content = f"{content1}\n\n{content2}"

        eq1 = section1.get("key_equations", [])
        eq2 = section2.get("key_equations", [])
        eq1 = eq1 if isinstance(eq1, list) else []
        eq2 = eq2 if isinstance(eq2, list) else []
        merged_equations = sorted(list(set(eq1 + eq2)))

        cit1 = section1.get("citations_used", [])
        cit2 = section2.get("citations_used", [])
        cit1 = cit1 if isinstance(cit1, list) else []
        cit2 = cit2 if isinstance(cit2, list) else []
        merged_citations = sorted(list(set(cit1 + cit2)))

        return make_merged_section(
            section1,
            section2,
            title=merged_title,
            content=merged_content,
            key_equations=merged_equations,
            citations_used=merged_citations,
            merged_from=[section1["section_id"], section2["section_id"]],
        )

    def _calculate_overlap(self, section1: Dict, section2: Dict) -> float:
        content1 = str(section1.get("content", "")).lower()
        content2 = str(section2.get("content", "")).lower()
        words1 = set(re.findall(r"\w+", content1))
        words2 = set(re.findall(r"\w+", content2))
        if not words1 or not words2:
            return 0.0
        return len(words1.intersection(words2)) / len(words1.union(words2))

    def should_merge(self, sections: List[Dict], overlap_score: float) -> bool:
        if len(sections) <= self.min_section_count:
            return False
        return overlap_score >= self.overlap_threshold
