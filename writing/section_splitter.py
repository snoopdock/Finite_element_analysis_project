#!/usr/bin/env python3
"""Section splitting logic for OAA Loop."""

import sys
from typing import Dict, List, Optional
from processing.llm_parser import LLMJSONParseError


SPLIT_SYSTEM = """You are an expert academic editor.
Your task is to split a long academic section into smaller, focused subsections.

CRITICAL: Respond with ONLY valid JSON. No markdown code fences, no explanation.
Use double quotes for all keys and string values. No single quotes. No trailing commas.

Return this exact JSON structure:
{
  "subsections": [
    {"title": "Subsection Title 1"},
    {"title": "Subsection Title 2"},
    {"title": "Subsection Title 3"}
  ]
}"""


class SectionSplitter:
    def __init__(self, config: Dict, prompt_generator):
        self.min_words = config.get("writing", {}).get("min_words_per_section", 150)
        self.min_concepts = config.get("writing", {}).get("min_concepts_mentioned", 2)
        self.prompt_generator = prompt_generator

    def is_too_simple(self, section: Dict, knowledge_base: Dict) -> bool:
        """Check if a section is too short or lacks conceptual depth."""
        content = section.get("content", "")
        if not content:
            return False
            
        words = content.split()
        if len(words) < self.min_words:
            return True
            
        concepts_mentioned = self._count_concepts_mentioned(content, knowledge_base)
        if concepts_mentioned < self.min_concepts:
            return True
            
        return False

    def generate_subsection_topics(self, title: str, content: str, provider, parser) -> Optional[List[str]]:
        """Use an LLM to generate logical subsection titles."""
        prompt = (
            f"The following academic section is too long and needs to be split into 2 to 4 smaller, "
            f"focused subsections.\n\n"
            f"Section Title: {title}\n\n"
            f"Content:\n{content[:2000]}...\n\n"
            f"Generate 2 to 4 distinct subsection titles that logically divide this content."
        )
        
        messages = [
            {"role": "system", "content": SPLIT_SYSTEM},
            {"role": "user", "content": prompt}
        ]
        
        text, error = provider.chat(messages, temperature=0.3, max_tokens=500)
        if error or not text:
            print(f"    [SectionSplitter] LLM error: {error}", file=sys.stderr)
            return None
            
        try:
            result = parser.parse(text, model_name="cloudflare")
            if isinstance(result, list) and len(result) > 0:
                result = result[0]
                
            subsections = result.get("subsections", [])
            topics = []
            for sub in subsections:
                if isinstance(sub, dict) and "title" in sub:
                    topics.append(sub["title"])
                elif isinstance(sub, str):
                    topics.append(sub)
                    
            if len(topics) >= 2:
                return topics
            return None
            
        except LLMJSONParseError as e:
            print(f"    [SectionSplitter] JSON parse error: {e.message}", file=sys.stderr)
            return None

    def _count_concepts_mentioned(self, content: str, kb: Dict) -> int:
        """Count how many knowledge base concepts are mentioned in the text."""
        content_lower = content.lower()
        count = 0
        concepts = kb.get("concepts", [])
        for concept in concepts:
            name = concept.get("name", "").lower()
            if name and name in content_lower:
                count += 1
        return count

    def split_section(self, section: Dict, subsection_topics: List[str]) -> List[Dict]:
        """
        LEGACY: Split a section into subsections, carrying over parent content to the first one.
        Kept for backward compatibility. Use split_section_safe() for OAA loop.
        """
        parent_title = section.get("title", "Untitled")
        parent_content = section.get("content", "") 
        
        subsections = []
        for i, topic in enumerate(subsection_topics):
            subsection = {
                "title": f"{parent_title}: {topic}",
                "content": parent_content if i == 0 else "", 
                "key_equations": section.get("key_equations", []) if i == 0 else [],
                "citations_used": section.get("citations_used", []) if i == 0 else [],
                "parent_section": parent_title,
                "subsection_index": i,
            }
            subsections.append(subsection)
        
        return subsections
    
    def split_section_safe(self, section: Dict, subsection_topics: List[str]) -> List[Dict]:
        """
        CRITICAL FIX: Split a section without duplicating content.
        Creates subsections with explicit state tracking.
        The parent content is preserved as reference but not copied into subsections.
        """
        parent_title = section.get("title", "Untitled")
        parent_content = section.get("content", "")

        subsections = []
        for i, topic in enumerate(subsection_topics):
            subsection = {
                "title": f"{parent_title}: {topic}",
                "content": "",  # Start empty, don't duplicate parent content
                "status": "needs_generation",  # Explicit state
                "parent_section": parent_title,
                "parent_content_reference": parent_content[:200] + "..." if len(parent_content) > 200 else parent_content,
                "generated_from": "split",
                "subsection_index": i,
                "key_equations": [],
                "citations_used": [],
            }
            subsections.append(subsection)

        return subsections
