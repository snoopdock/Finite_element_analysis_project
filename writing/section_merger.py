#!/usr/bin/env python3
"""Section Merger - Merges adjacent sections that are semantically similar."""

import re
from typing import Dict, List, Tuple

class SectionMerger:
    def __init__(self, config: Dict):
        self.overlap_threshold = config.get("merging", {}).get("overlap_threshold", 0.6)
        self.min_section_count = config.get("merging", {}).get("min_section_count", 3)
    
    def find_merge_candidates(self, sections: List[Dict]) -> List[Tuple[int, int, float]]:
        """Only check adjacent sections for merging."""
        candidates = []
        for i in range(len(sections) - 1):
            sec1 = sections[i]
            sec2 = sections[i + 1]
            overlap = self._calculate_overlap(sec1, sec2)
            if overlap >= self.overlap_threshold:
                candidates.append((i, i + 1, overlap))
        
        candidates.sort(key=lambda x: x[2], reverse=True)
        return candidates
    
    def merge_sections(self, section1: Dict, section2: Dict) -> Dict:
        title1 = section1.get("title", "")
        title2 = section2.get("title", "")
        merged_title = f"{title1} (merged with {title2})"
        
        content1 = section1.get("content", "")
        content2 = section2.get("content", "")
        merged_content = f"{content1}\n\n{content2}"
        
        eq1 = section1.get("key_equations", [])
        eq2 = section2.get("key_equations", [])
        merged_equations = sorted(list(set(eq1 + eq2)))
        
        cit1 = section1.get("citations_used", [])
        cit2 = section2.get("citations_used", [])
        merged_citations = sorted(list(set(cit1 + cit2)))
        
        return {
            "title": merged_title,
            "content": merged_content,
            "key_equations": merged_equations,
            "citations_used": merged_citations,
            "merged_from": [title1, title2],
        }
    
    def _calculate_overlap(self, section1: Dict, section2: Dict) -> float:
        content1 = section1.get("content", "").lower()
        content2 = section2.get("content", "").lower()
        words1 = set(re.findall(r'\w+', content1))
        words2 = set(re.findall(r'\w+', content2))
        if not words1 or not words2:
            return 0.0
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        return len(intersection) / len(union)
    
    def should_merge(self, sections: List[Dict], overlap_score: float) -> bool:
        if len(sections) <= self.min_section_count:
            return False
        return overlap_score >= self.overlap_threshold
