#!/usr/bin/env python3
"""Section splitting logic for OAA Loop."""

import re
import sys
from typing import Dict, List, Optional

from processing.llm_parser import LLMJSONParseError
from core.section_identity import ensure_section_id, make_child_section


SPLIT_SYSTEM = """You are an expert academic editor.

Your task is to split a long academic section into smaller,
focused subsections.

CRITICAL:
Respond with ONLY valid JSON.
No markdown code fences.
No explanation.

Return exactly:

{
  "subsections": [
    {"title": "Subsection Title 1"},
    {"title": "Subsection Title 2"},
    {"title": "Subsection Title 3"}
  ]
}

Rules:
- Generate 2 to 4 subsections.
- Titles must be academically meaningful.
- Titles must be distinct.
- Do not invent subjects that are absent from the supplied section.
"""


class SectionSplitter:
    def __init__(self, config: Dict, prompt_generator=None):
        self.min_words = int(config.get("writing", {}).get("min_words_per_section", 150))
        self.min_concepts = int(config.get("writing", {}).get("min_concepts_mentioned", 2))
        self.prompt_generator = prompt_generator

    def is_too_simple(self, section: Dict, knowledge_base: Dict) -> bool:
        if not isinstance(section, dict):
            return False
        content = section.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        content = content.strip()
        if not content:
            return False
        if len(content.split()) < self.min_words:
            return True
        return self._count_concepts_mentioned(content, knowledge_base) < self.min_concepts

    def generate_subsection_topics(self, title: str, content: str, provider, parser) -> Optional[List[str]]:
        if not title or not content:
            return None

        prompt = (
            "The following academic section is too long and needs "
            "to be split into 2 to 4 smaller, focused subsections.\n\n"
            f"Section Title: {title}\n\nContent:\n{content[:6000]}\n\n"
            "Generate 2 to 4 distinct subsection titles that logically divide the supplied content."
        )

        messages = [
            {"role": "system", "content": SPLIT_SYSTEM},
            {"role": "user", "content": prompt},
        ]

        text, error = provider.chat(messages, temperature=0.3, max_tokens=500)
        if error or not text or not isinstance(text, str):
            if error:
                print(f"    [SectionSplitter] LLM error: {error}", file=sys.stderr)
            return None

        try:
            result = parser.parse(text, model_name="cloudflare")
        except LLMJSONParseError as exc:
            print(f"    [SectionSplitter] JSON parse error: {exc.message}", file=sys.stderr)
            return None
        except Exception as exc:
            print(f"    [SectionSplitter] Parser error: {exc}", file=sys.stderr)
            return None

        if isinstance(result, list):
            if not result:
                return None
            result = result[0]
        if not isinstance(result, dict):
            return None

        subsections = result.get("subsections", [])
        if not isinstance(subsections, list):
            return None

        topics: List[str] = []
        seen = set()
        for subsection in subsections:
            candidate = subsection.get("title") if isinstance(subsection, dict) else subsection
            if not isinstance(candidate, str):
                continue
            candidate = candidate.strip()
            if not candidate:
                continue
            normalized = re.sub(r"\s+", " ", candidate.lower())
            if normalized in seen:
                continue
            seen.add(normalized)
            topics.append(candidate)

        return topics[:4] if len(topics) >= 2 else None

    def _count_concepts_mentioned(self, content: str, kb: Dict) -> int:
        if not isinstance(kb, dict):
            return 0
        normalized_content = re.sub(r"\s+", " ", content.lower())
        concepts = kb.get("concepts", [])
        if not isinstance(concepts, list):
            return 0

        count = 0
        seen_names = set()
        for concept in concepts:
            if not isinstance(concept, dict):
                continue
            name = concept.get("name", "")
            if not isinstance(name, str):
                continue
            name = re.sub(r"\s+", " ", name.lower()).strip()
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            if name in normalized_content:
                count += 1
        return count

    def split_section(self, section: Dict, subsection_topics: List[str]) -> List[Dict]:
        """Legacy split implementation retained for compatibility.

        Unlike the historical implementation, every child now receives a new
        UUID and records the parent UUID.
        """
        parent_title = section.get("title", "Untitled") if isinstance(section, dict) else "Untitled"
        parent_content = section.get("content", "") if isinstance(section, dict) else ""
        ensure_section_id(section)

        subsections = []
        for index, topic in enumerate(subsection_topics):
            if not isinstance(topic, str) or not topic.strip():
                continue
            child = make_child_section(
                section,
                title=f"{parent_title}: {topic.strip()}",
                content=parent_content if index == 0 else "",
                key_equations=section.get("key_equations", []) if index == 0 else [],
                citations_used=section.get("citations_used", []) if index == 0 else [],
                subsection_index=index,
                status="complete" if index == 0 and parent_content else "needs_generation",
            )
            subsections.append(child)
        return subsections

    def split_section_safe(self, section: Dict, subsection_topics: List[str]) -> List[Dict]:
        """Split a section without duplicating its content."""
        parent_title = section.get("title", "Untitled")
        parent_content = section.get("content", "")
        if not isinstance(parent_content, str):
            parent_content = str(parent_content)
        if not isinstance(subsection_topics, list):
            return []

        ensure_section_id(section)
        subsections = []
        seen_titles = set()

        for index, topic in enumerate(subsection_topics):
            if not isinstance(topic, str) or not topic.strip():
                continue
            full_title = f"{parent_title}: {topic.strip()}"
            normalized_title = re.sub(r"\s+", " ", full_title.lower())
            if normalized_title in seen_titles:
                continue
            seen_titles.add(normalized_title)

            reference = parent_content[:500]
            if len(parent_content) > 500:
                reference += "..."

            child = make_child_section(
                section,
                title=full_title,
                content="",
                status="needs_generation",
                parent_content_reference=reference,
                subsection_index=index,
                key_equations=[],
                citations_used=[],
            )
            subsections.append(child)

        return subsections
