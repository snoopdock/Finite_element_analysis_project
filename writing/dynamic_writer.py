#!/usr/bin/env python3
"""Dynamic academic writer with stable section identity and ranked evidence."""

from __future__ import annotations

import re
import sys
import time
from typing import Dict, List, Optional, Set, Tuple

from analysis.writing_indicator import WritingIndicator
from core.section_identity import ensure_section_id
from research.ranking import rank_knowledge_items
from utils.text import kb_to_prompt_text


def calculate_word_overlap(text1: str, text2: str) -> float:
    words1 = set(re.findall(r"\w+", str(text1).lower()))
    words2 = set(re.findall(r"\w+", str(text2).lower()))
    if not words1 or not words2:
        return 0.0
    return len(words1.intersection(words2)) / len(words1.union(words2))


def _strip_bad_citations(text: str, allowed_sources: Set[str]) -> str:
    def replace(match):
        raw = match.group(1).strip()
        if not re.fullmatch(r"[\w.\-]+(?:,\s*[\w.\-]+)*", raw):
            return match.group(0)
        parts = [part.strip() for part in raw.split(",") if part.strip()]
        valid = [part for part in parts if part in allowed_sources]
        return "[" + ", ".join(valid) + "]" if valid else ""

    return re.sub(r"\[([^\]]+)\]", replace, str(text))


def _extract_equations(content: str) -> List[str]:
    equations: List[str] = []
    equations.extend(re.findall(r"\\\[(.+?)\\\]", content, re.DOTALL))
    equations.extend(re.findall(r"\$\$(.+?)\$\$", content, re.DOTALL))
    equations.extend(
        re.findall(
            r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)",
            content,
            re.DOTALL,
        )
    )

    result = []
    seen = set()
    for equation in equations:
        equation = equation.strip()
        if equation and equation not in seen:
            seen.add(equation)
            result.append(equation)
    return result


def _extract_citations(
    content: str,
    allowed_sources: Optional[Set[str]] = None,
) -> List[str]:
    allowed_sources = allowed_sources or set()
    citations = re.findall(
        r"\[([\w.\-]+(?:,\s*[\w.\-]+)*)\]",
        content,
    )
    result = set()
    for group in citations:
        for part in group.split(","):
            part = part.strip()
            if not part:
                continue
            if allowed_sources and part not in allowed_sources:
                continue
            result.add(part)
    return sorted(result)


class DynamicWriter:
    def __init__(
        self,
        provider,
        parser,
        config,
        iteration_history,
        writing_indicator: Optional[WritingIndicator] = None,
    ):
        self.provider = provider
        self.parser = parser
        self.config = config
        self.history = iteration_history

        writing_config = config.get("writing", {})
        budget_config = config.get("budget", {})

        self.indicator = writing_indicator or WritingIndicator(
            w_L=writing_config.get("w_L", 0.4),
            w_U=writing_config.get("w_U", 0.4),
            w_A=writing_config.get("w_A", 0.2),
            leverage_map=config.get("section_leverage") or None,
        )

        self.theta = float(
            writing_config.get("theta", 0.75)
        )
        self.tau = float(
            writing_config.get("tau", 0.6)
        )
        self.max_calls = int(
            budget_config.get("max_llm_calls_per_run", 20)
        )
        self.max_tokens = int(
            budget_config.get("max_tokens_per_call", 2500)
        )
        self.max_retries_per_paragraph = max(
            1,
            int(
                writing_config.get(
                    "max_retries_per_paragraph",
                    2,
                )
            ),
        )
        self.top_k_evidence = max(
            1,
            int(
                writing_config.get(
                    "top_k_knowledge_items",
                    6,
                )
            ),
        )

    def select_model(self, eta: float) -> str:
        models = self.config.get(
            "cloudflare_models",
            ["@cf/meta/llama-3.1-8b-instruct"],
        )
        if not isinstance(models, list) or not models:
            raise RuntimeError(
                "cloudflare_models must contain at least one model."
            )
        return models[0] if eta >= self.tau else models[-1]

    def mark_sections(
        self,
        section_topics: List[str],
    ) -> List[str]:
        indicators: List[Tuple[str, float]] = []

        for topic in section_topics:
            if not topic:
                continue
            eta = float(
                self.indicator.compute(
                    topic,
                    self.history,
                )
            )
            indicators.append(
                (topic, eta)
            )

        indicators.sort(
            key=lambda pair: (-pair[1], pair[0])
        )

        if not indicators:
            return []

        total_eta = sum(
            eta
            for _, eta in indicators
        )

        if total_eta <= 0:
            return [
                topic
                for topic, _ in indicators[:2]
            ]

        target = self.theta * total_eta
        selected = []
        cumulative = 0.0

        for topic, eta in indicators:
            selected.append(topic)
            cumulative += eta
            if cumulative >= target:
                break

        return selected

    def _get_relevant_concepts(
        self,
        topic: str,
        kb: Dict,
    ) -> List[Dict]:
        ranked = rank_knowledge_items(
            topic,
            kb,
            top_k=self.top_k_evidence,
        )

        relevant = []

        for item in ranked:
            item_type = item.get(
                "item_type",
                "concept",
            )

            name = (
                item.get("name")
                or item.get("title")
                or item.get("rule")
                or "Unknown"
            )

            explanation = (
                item.get("explanation")
                or item.get("description")
                or ""
            )

            math = (
                item.get("mathematical_formulation")
                or item.get("latex")
                or ""
            )

            sources = item.get(
                "source_ids",
                [],
            )

            if not isinstance(
                sources,
                list,
            ):
                sources = []

            relevant.append(
                {
                    "type": str(item_type),
                    "name": str(name),
                    "explanation": str(explanation),
                    "math": str(math),
                    "source_ids": [
                        str(source)
                        for source in sources
                        if source
                    ],
                    "ranking": item.get(
                        "ranking",
                        {},
                    ),
                }
            )

        return relevant

    def write_section(
        self,
        topic: str,
        kb: Dict,
        errors: List[str],
        document_map: List[Dict],
        existing_section: Optional[Dict] = None,
    ) -> Optional[Dict]:
        eta = self.indicator.compute(
            existing_section or topic,
            self.history,
        )

        model = self.select_model(eta)

        print(
            f"    [DynamicWriter] Section: {topic}, "
            f"eta={eta:.2f}, model={model}",
            file=sys.stderr,
        )

        outline = self._generate_outline(
            topic,
            kb,
            model,
        )

        if not outline:
            errors.append(
                f"Section '{topic}': outline generation failed"
            )
            return None

        paragraphs = []

        for index, paragraph_topic in enumerate(
            outline
        ):
            if self.provider.budget_exhausted():
                print(
                    "    [DynamicWriter] Budget exhausted "
                    f"at paragraph {index + 1}",
                    file=sys.stderr,
                )
                break

            paragraph = None

            for retry in range(
                self.max_retries_per_paragraph
            ):
                paragraph = self._draft_paragraph(
                    topic,
                    paragraph_topic,
                    kb,
                    model,
                    index,
                    len(outline),
                    paragraphs,
                    document_map,
                )

                if paragraph is not None:
                    break

                if retry + 1 < self.max_retries_per_paragraph:
                    time.sleep(1)

            if paragraph:
                paragraphs.append(
                    paragraph
                )
            else:
                errors.append(
                    f"Section '{topic}': paragraph "
                    f"{index + 1} failed after "
                    f"{self.max_retries_per_paragraph} attempts"
                )

        if not paragraphs:
            return None

        section = self._assemble_section(
            topic,
            paragraphs,
        )

        if existing_section is not None:
            section["section_id"] = ensure_section_id(
                existing_section
            )

            for key in (
                "parent_section_ids",
                "generated_from",
                "subsection_index",
            ):
                if key in existing_section:
                    section[key] = existing_section[key]

            if "parent_content_reference" in existing_section:
                section[
                    "parent_content_reference"
                ] = existing_section[
                    "parent_content_reference"
                ]
        else:
            ensure_section_id(section)
            section["generated_from"] = "writer"

        section["status"] = (
            "complete"
            if self._validate_section(section)
            else "incomplete"
        )

        if section["status"] == "complete":
            self.history.record_clean_audit(
                section
            )
        else:
            self.history.record_failed_audit(
                section
            )

        return section

    def _generate_outline(
        self,
        topic: str,
        kb: Dict,
        model: str,
    ) -> Optional[List[str]]:
        concepts = self._get_relevant_concepts(
            topic,
            kb,
        )

        concept_names = [
            concept["name"]
            for concept in concepts[:6]
        ]

        kb_display = kb_to_prompt_text(
            kb,
            max_chars=2000,
        )

        prompt = (
            f'Generate exactly 3 distinct paragraph topics for a section '
            f'titled "{topic}".\n'
            f"Available ranked concepts: {', '.join(concept_names)}\n"
            f"Knowledge base summary:\n{kb_display}\n"
            "Ensure the topics are mutually exclusive and collectively "
            "cover the section.\n"
            "Return ONLY valid JSON:\n"
            '{"outline": ["topic 1", "topic 2", "topic 3"]}'
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You generate section outlines. "
                    "Return ONLY valid JSON."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]

        result, error = self._call_llm(
            messages,
            model,
            temperature=0.3,
            max_tokens=500,
        )

        if error or not result:
            return None

        if isinstance(result, dict):
            outline = result.get(
                "outline"
            )
        elif isinstance(result, list):
            outline = result
        else:
            outline = None

        if not isinstance(
            outline,
            list,
        ):
            return None

        cleaned = []
        seen = set()

        for item in outline:
            if not isinstance(
                item,
                str,
            ):
                continue

            item = re.sub(
                r"\s+",
                " ",
                item.strip(),
            )

            key = item.lower()

            if item and key not in seen:
                seen.add(key)
                cleaned.append(item)

        return (
            cleaned[:3]
            if len(cleaned) >= 3
            else None
        )

    def _draft_paragraph(
        self,
        section_topic: str,
        para_topic: str,
        kb: Dict,
        model: str,
        para_index: int,
        total_paras: int,
        previous_paragraphs: List[str],
        document_map: List[Dict],
    ) -> Optional[str]:
        concepts = self._get_relevant_concepts(
            para_topic + " " + section_topic,
            kb,
        )

        allowed_sources: Set[str] = set()
        evidence_blocks = []

        for concept in concepts:
            sources = concept.get(
                "source_ids",
                [],
            )

            allowed_sources.update(
                sources
            )

            source_text = ", ".join(
                f"[{sid}]"
                for sid in sources
            )

            evidence_blocks.append(
                f"- {concept['type'].upper()}: "
                f"{concept['name']}\n"
                f"  Fact: {concept['explanation'][:500]}\n"
                f"  Math: {concept.get('math', '')}\n"
                f"  Allowed Citation: {source_text}\n"
            )

        evidence_text = (
            "\n".join(evidence_blocks)
            if evidence_blocks
            else "No directly matched knowledge-base item was found."
        )

        previous_context = ""

        if previous_paragraphs:
            previous_context = (
                "\nALREADY WRITTEN IN THIS SECTION "
                "(do NOT repeat):\n"
            )

            for index, previous in enumerate(
                previous_paragraphs
            ):
                previous_context += (
                    f"  Para {index + 1}: "
                    f"{previous[:250]}...\n"
                )

        doc_context = ""

        if document_map:
            doc_context = (
                "\nPREVIOUS SECTIONS IN DOCUMENT:\n"
            )

            for item in document_map:
                doc_context += (
                    f"- {item['title']}: "
                    f"{item['summary']}\n"
                )

        allowed_text = (
            ", ".join(
                sorted(allowed_sources)
            )
            if allowed_sources
            else "none"
        )

        prompt = f'''Write ONE academic paragraph of 100-150 words about: {para_topic}
Section: {section_topic}
Paragraph position: {para_index + 1} of {total_paras}
{doc_context}
{previous_context}

Use ONLY the following ranked evidence:
{evidence_text}

CRITICAL RULES:
1. Only make claims supported by the supplied evidence.
2. Only use these exact citation IDs: {allowed_text}
3. Do not repeat information from previous paragraphs.
4. Do not begin with meta-text such as "This chapter" or "This section".
5. Write only the paragraph text.
6. No JSON, no markdown, and no title.
7. Use $math$ for inline equations.
'''

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an academic technical writer. "
                    "Use only the supplied evidence and valid citations."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]

        result, error = self._call_llm(
            messages,
            model,
            temperature=0.4,
            max_tokens=800,
        )

        if error:
            return None

        if isinstance(result, dict):
            result = result.get(
                "content",
                "",
            )

        if not isinstance(
            result,
            str,
        ):
            return None

        text = result.strip()

        if any(
            calculate_word_overlap(
                text,
                previous,
            ) > 0.50
            for previous in previous_paragraphs
        ):
            return None

        text = _strip_bad_citations(
            text,
            allowed_sources,
        )

        text = re.sub(
            r"(?i)^\s*This (?:chapter|section|document|paragraph) "
            r"(?:provides|discusses|explores|covers|outlines).*?\.\s*",
            "",
            text,
        )

        text = re.sub(
            r"(?i)^\s*In this (?:chapter|section), we will.*?\.\s*",
            "",
            text,
        )

        text = re.sub(
            r"\s+",
            " ",
            text,
        ).strip()

        return (
            text
            if len(text.split()) > 20
            else None
        )

    def _assemble_section(
        self,
        topic: str,
        paragraphs: List[str],
    ) -> Dict:
        content = "\n\n".join(
            paragraphs
        )

        return {
            "title": topic,
            "content": content,
            "key_equations": _extract_equations(
                content
            )[:5],
            "citations_used": _extract_citations(
                content
            ),
        }

    def _validate_section(
        self,
        section: Dict,
    ) -> bool:
        title = section.get(
            "title"
        )

        content = section.get(
            "content",
            "",
        )

        return (
            isinstance(title, str)
            and bool(title.strip())
            and isinstance(content, str)
            and len(content.split()) >= 100
        )

    def _call_llm(
        self,
        messages,
        model,
        temperature=0.3,
        max_tokens=1000,
    ):
        if self.provider.budget_exhausted():
            return (
                None,
                "Local logical-call budget exhausted",
            )

        text, error = self.provider.chat(
            messages,
            temperature,
            max_tokens,
            model=model,
        )

        if error:
            return None, error

        if not text or not str(text).strip():
            return None, "Empty response"

        user_content = "\n".join(
            message.get("content", "")
            for message in messages
            if message.get("role") == "user"
        )

        expects_json = (
            "Return ONLY valid JSON"
            in user_content
        )

        if not expects_json:
            return str(text).strip(), None

        try:
            return (
                self.parser.parse(
                    text,
                    model_name=model,
                ),
                None,
            )
        except Exception as exc:
            return None, f"Parse error: {exc}"

    @staticmethod
    def _retired_section_ids(
        sections: List[Dict],
    ) -> Set[str]:
        """IDs of sections that have become parents of live sections."""
        retired = set()

        for section in sections:
            if not isinstance(
                section,
                dict,
            ):
                continue

            for parent_id in section.get(
                "parent_section_ids",
                [],
            ):
                if parent_id:
                    retired.add(
                        str(parent_id)
                    )

        return retired

    def run(
        self,
        section_topics: List[str],
        kb: Dict,
        existing_sections: List[Dict],
        errors: List[str],
    ) -> Tuple[List[Dict], int]:
        print(
            "\n=== PHASE 3: DYNAMIC WRITE ===",
            file=sys.stderr,
        )

        existing_sections = [
            section
            for section in existing_sections
            if isinstance(section, dict)
        ]

        existing_by_id = {}
        existing_by_title = {}

        for section in existing_sections:
            section_id = ensure_section_id(
                section
            )

            existing_by_id[
                section_id
            ] = section

            title = str(
                section.get(
                    "title",
                    "",
                )
            ).strip().lower()

            if title:
                existing_by_title[
                    title
                ] = section

            self.history.register_section(
                section
            )

        retired_ids = self._retired_section_ids(
            existing_sections
        )

        marked = self.mark_sections(
            section_topics
        )

        # A topic whose historical section ID is now a parent of a live
        # section is retired. Do not recreate it from configuration.
        active_topics = []

        for topic in marked:
            history_key = (
                self.history.resolve_section_key(
                    topic
                )
            )

            if (
                history_key in retired_ids
                and history_key not in existing_by_id
            ):
                print(
                    "    [DynamicWriter] Skipping retired "
                    f"section topic: {topic}",
                    file=sys.stderr,
                )
                continue

            active_topics.append(topic)

        marked = active_topics

        print(
            f"  Marked {len(marked)}/{len(section_topics)} sections: {marked}",
            file=sys.stderr,
        )

        all_sections = list(
            existing_sections
        )

        sections_written = 0

        document_map = []

        for section in existing_sections:
            content = str(
                section.get(
                    "content",
                    "",
                )
            )

            summary = (
                content[:200]
                .replace("\n", " ")
                + (
                    "..."
                    if len(content) > 200
                    else ""
                )
            )

            document_map.append(
                {
                    "section_id": section.get(
                        "section_id"
                    ),
                    "title": str(
                        section.get(
                            "title",
                            "",
                        )
                    ),
                    "summary": summary,
                }
            )

        for topic in marked:
            if self.provider.budget_exhausted():
                print(
                    "  Budget exhausted. Stopping.",
                    file=sys.stderr,
                )
                break

            history_key = (
                self.history.resolve_section_key(
                    topic
                )
            )

            existing = existing_by_id.get(
                history_key
            )

            if existing is None:
                existing = existing_by_title.get(
                    str(topic).strip().lower()
                )

            section = self.write_section(
                topic,
                kb,
                errors,
                document_map,
                existing_section=existing,
            )

            if section is None:
                continue

            section_id = ensure_section_id(
                section
            )

            replaced = False

            for index, candidate in enumerate(
                all_sections
            ):
                if (
                    isinstance(candidate, dict)
                    and candidate.get(
                        "section_id"
                    ) == section_id
                ):
                    all_sections[index] = section
                    replaced = True
                    break

            if not replaced:
                all_sections.append(
                    section
                )

            sections_written += 1

            content = str(
                section.get(
                    "content",
                    "",
                )
            )

            document_map.append(
                {
                    "section_id": section_id,
                    "title": topic,
                    "summary": (
                        content[:200]
                        .replace("\n", " ")
                        + (
                            "..."
                            if len(content) > 200
                            else ""
                        )
                    ),
                }
            )

        return (
            all_sections,
            sections_written,
        )
