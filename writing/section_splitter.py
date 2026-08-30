#!/usr/bin/env python3
"""Section splitting logic for OAA Loop."""

import re
import sys
from typing import Dict, List, Optional

from processing.llm_parser import LLMJSONParseError


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
    def __init__(
        self,
        config: Dict,
        prompt_generator=None,
    ):
        self.min_words = int(
            config.get("writing", {}).get(
                "min_words_per_section",
                150,
            )
        )

        self.min_concepts = int(
            config.get("writing", {}).get(
                "min_concepts_mentioned",
                2,
            )
        )

        # Kept for backward compatibility.
        # The current implementation generates its own prompt.
        self.prompt_generator = prompt_generator

    def is_too_simple(
        self,
        section: Dict,
        knowledge_base: Dict,
    ) -> bool:
        """Check whether a section lacks sufficient depth."""

        if not isinstance(section, dict):
            return False

        content = section.get("content", "")

        if not isinstance(content, str):
            content = str(content)

        content = content.strip()

        if not content:
            return False

        words = content.split()

        if len(words) < self.min_words:
            return True

        concepts_mentioned = (
            self._count_concepts_mentioned(
                content,
                knowledge_base,
            )
        )

        if concepts_mentioned < self.min_concepts:
            return True

        return False

    def generate_subsection_topics(
        self,
        title: str,
        content: str,
        provider,
        parser,
    ) -> Optional[List[str]]:
        """Use an LLM to generate logical subsection titles."""

        if not title:
            return None

        if not content:
            return None

        prompt = (
            "The following academic section is too long and needs "
            "to be split into 2 to 4 smaller, focused subsections.\n\n"
            f"Section Title: {title}\n\n"
            f"Content:\n{content[:6000]}\n\n"
            "Generate 2 to 4 distinct subsection titles that "
            "logically divide the supplied content."
        )

        messages = [
            {
                "role": "system",
                "content": SPLIT_SYSTEM,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]

        text, error = provider.chat(
            messages,
            temperature=0.3,
            max_tokens=500,
        )

        if error:
            print(
                f"    [SectionSplitter] LLM error: {error}",
                file=sys.stderr,
            )
            return None

        if not text or not isinstance(text, str):
            print(
                "    [SectionSplitter] Empty LLM response.",
                file=sys.stderr,
            )
            return None

        try:
            result = parser.parse(
                text,
                model_name="cloudflare",
            )

        except LLMJSONParseError as exc:
            print(
                f"    [SectionSplitter] JSON parse error: "
                f"{exc.message}",
                file=sys.stderr,
            )
            return None

        except Exception as exc:
            print(
                f"    [SectionSplitter] Parser error: {exc}",
                file=sys.stderr,
            )
            return None

        if isinstance(result, list):
            if not result:
                return None

            result = result[0]

        if not isinstance(result, dict):
            return None

        subsections = result.get(
            "subsections",
            [],
        )

        if not isinstance(subsections, list):
            return None

        topics: List[str] = []
        seen = set()

        for subsection in subsections:
            if isinstance(subsection, dict):
                candidate = subsection.get("title")
            elif isinstance(subsection, str):
                candidate = subsection
            else:
                continue

            if not isinstance(candidate, str):
                continue

            candidate = candidate.strip()

            if not candidate:
                continue

            normalized = re.sub(
                r"\s+",
                " ",
                candidate.lower(),
            )

            if normalized in seen:
                continue

            seen.add(normalized)
            topics.append(candidate)

        if len(topics) < 2:
            return None

        return topics[:4]

    def _count_concepts_mentioned(
        self,
        content: str,
        kb: Dict,
    ) -> int:
        """
        Count knowledge-base concepts mentioned in the section.

        Matching is normalized rather than relying only on exact
        case-sensitive input.
        """

        if not isinstance(kb, dict):
            return 0

        normalized_content = re.sub(
            r"\s+",
            " ",
            content.lower(),
        )

        count = 0
        seen_names = set()

        concepts = kb.get(
            "concepts",
            [],
        )

        if not isinstance(concepts, list):
            return 0

        for concept in concepts:
            if not isinstance(concept, dict):
                continue

            name = concept.get(
                "name",
                "",
            )

            if not isinstance(name, str):
                continue

            name = re.sub(
                r"\s+",
                " ",
                name.lower(),
            ).strip()

            if not name or name in seen_names:
                continue

            seen_names.add(name)

            if name in normalized_content:
                count += 1

        return count

    def split_section(
        self,
        section: Dict,
        subsection_topics: List[str],
    ) -> List[Dict]:
        """
        Legacy split implementation.

        Kept for backward compatibility.
        New OAA code should use split_section_safe().
        """

        parent_title = (
            section.get(
                "title",
                "Untitled",
            )
            if isinstance(section, dict)
            else "Untitled"
        )

        parent_content = (
            section.get(
                "content",
                "",
            )
            if isinstance(section, dict)
            else ""
        )

        subsections = []

        for index, topic in enumerate(
            subsection_topics
        ):
            if not isinstance(topic, str):
                continue

            topic = topic.strip()

            if not topic:
                continue

            subsection = {
                "title": f"{parent_title}: {topic}",
                "content": (
                    parent_content
                    if index == 0
                    else ""
                ),
                "key_equations": (
                    section.get(
                        "key_equations",
                        [],
                    )
                    if index == 0
                    else []
                ),
                "citations_used": (
                    section.get(
                        "citations_used",
                        [],
                    )
                    if index == 0
                    else []
                ),
                "parent_section": parent_title,
                "subsection_index": index,
                "status": (
                    "complete"
                    if index == 0 and parent_content
                    else "needs_generation"
                ),
            }

            subsections.append(subsection)

        return subsections

    def split_section_safe(
        self,
        section: Dict,
        subsection_topics: List[str],
    ) -> List[Dict]:
        """
        Split a section without duplicating parent content.

        The old content is retained only as a short reference.
        The newly created subsections start empty and are explicitly
        marked as needing generation.
        """

        parent_title = section.get(
            "title",
            "Untitled",
        )

        parent_content = section.get(
            "content",
            "",
        )

        if not isinstance(parent_content, str):
            parent_content = str(parent_content)

        if not isinstance(subsection_topics, list):
            return []

        subsections = []

        seen_titles = set()

        for index, topic in enumerate(
            subsection_topics
        ):
            if not isinstance(topic, str):
                continue

            topic = topic.strip()

            if not topic:
                continue

            full_title = (
                f"{parent_title}: {topic}"
            )

            normalized_title = (
                full_title.lower()
            )

            if normalized_title in seen_titles:
                continue

            seen_titles.add(
                normalized_title
            )

            reference = parent_content[:500]

            if len(parent_content) > 500:
                reference += "..."

            subsection = {
                "title": full_title,
                "content": "",
                "status": "needs_generation",
                "parent_section": parent_title,
                "parent_content_reference": reference,
                "generated_from": "split",
                "subsection_index": index,
                "key_equations": [],
                "citations_used": [],
            }

            subsections.append(
                subsection
            )

        return subsections
