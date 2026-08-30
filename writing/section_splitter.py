#!/usr/bin/env python3
"""Section Splitter - Expands sections that are 'too simple'."""

import json
import re
from typing import Dict, List, Optional

class SectionSplitter:
    def __init__(self, config: Dict):
        self.min_word_count = config.get("splitting", {}).get("min_word_count", 300)
        self.min_concept_coverage = config.get("splitting", {}).get("min_concept_coverage", 3)
        self.max_subsections = config.get("splitting", {}).get("max_subsections", 3)
    
    def is_too_simple(self, section: Dict, knowledge_base: Dict) -> bool:
        content = section.get("content", "")
        word_count = len(content.split())
        concept_count = self._count_concepts_mentioned(content, knowledge_base)
        
        # Don't flag empty sections that are already subsections waiting to be written
        if word_count == 0 and ": " in section.get("title", ""):
            return False
            
        too_few_words = word_count < self.min_word_count
        too_few_concepts = concept_count < self.min_concept_coverage
        
        return too_few_words or too_few_concepts
    
    def generate_subsection_topics(self, section_title: str, section_content: str, provider, parser) -> Optional[List[str]]:
        prompt = f"""The following section is too short and needs to be split into {self.max_subsections} subsections.
Section title: {section_title}
Current content (first 500 chars): {section_content[:500]}
Generate exactly {self.max_subsections} subsection topics that would expand this section.
Return ONLY valid JSON: {{"subsections": ["topic 1", "topic 2", "topic 3"]}}"""
        
        messages = [
            {"role": "system", "content": "You generate subsection topics. Return ONLY valid JSON."},
            {"role": "user", "content": prompt},
        ]
        
        text, error = provider.chat(messages, temperature=0.3, max_tokens=500)
        if error or not text:
            return None
        
        try:
            result = parser.parse(text, model_name="cloudflare")
            if isinstance(result, dict) and "subsections" in result:
                return result["subsections"][:self.max_subsections]
        except Exception:
            pass
        return None
    
    def split_section(self, section: Dict, subsection_topics: List[str]) -> List[Dict]:
        parent_title = section.get("title", "Untitled")
        parent_content = section.get("content", "") 
        
        subsections = []
        for i, topic in enumerate(subsection_topics):
            subsection = {
                "title": f"{parent_title}: {topic}",
                # Carry over parent content to the first subsection as fallback
                "content": parent_content if i == 0 else "", 
                "key_equations": section.get("key_equations", []) if i == 0 else [],
                "citations_used": section.get("citations_used", []) if i == 0 else [],
                "parent_section": parent_title,
                "subsection_index": i,
            }
            subsections.append(subsection)
        
        return subsections
    
    def _count_concepts_mentioned(self, content: str, kb: Dict) -> int:
        content_lower = content.lower()
        count = 0
        concepts = kb.get("concepts", [])
        for concept in concepts:
            name = concept.get("name", "").lower()
            if name and name in content_lower:
                count += 1
        return count
