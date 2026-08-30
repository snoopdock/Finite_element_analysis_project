#!/usr/bin/env python3
"""Dynamic Writer with sub-task decomposition and algorithmic guardrails."""

import json
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple, Set

from analysis.writing_indicator import WritingIndicator
from analysis.iteration_history import IterationHistory
from utils.text import kb_to_prompt_text


def calculate_word_overlap(text1: str, text2: str) -> float:
    words1 = set(re.findall(r'\w+', text1.lower()))
    words2 = set(re.findall(r'\w+', text2.lower()))
    if not words1 or not words2:
        return 0.0
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    return len(intersection) / len(union)


def _strip_bad_citations(text: str, allowed_sources: Set[str]) -> str:
    """
    Strip hallucinated citations without destroying LaTeX math.
    Only strips brackets whose contents look like citation IDs.
    """
    def replace_if_bad(m):
        b = m.group(1).strip()
        # Only match citation-like IDs (word chars, dots, hyphens, underscores)
        if re.fullmatch(r'[\w\.\-]+(?:,\s*[\w\.\-]+)*', b) and b not in allowed_sources:
            return ""
        return m.group(0)
    return re.sub(r'\[([^\]]+)\]', replace_if_bad, text)


def _extract_equations(content: str) -> List[str]:
    """Extract equations matching \\[...\\], $$...$$, and $...$ formats."""
    equations = []
    equations.extend(re.findall(r'\\\[(.+?)\\\]', content, re.DOTALL))
    equations.extend(re.findall(r'\$\$(.+?)\$\$', content, re.DOTALL))
    if not equations:
        equations.extend(re.findall(r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)', content))
    return [eq.strip() for eq in equations if eq.strip()]


def _extract_citations(content: str) -> List[str]:
    """Extract only valid citation IDs."""
    citations = re.findall(r'\[([\w\.\-]+(?:,\s*[\w\.\-]+)*)\]', content)
    result = []
    for c in citations:
        for part in c.split(','):
            part = part.strip()
            if part:
                result.append(part)
    return sorted(set(result))


class DynamicWriter:
    def __init__(self, provider, parser, config, iteration_history):
        self.provider = provider
        self.parser = parser
        self.config = config
        self.history = iteration_history
        self.indicator = WritingIndicator(
            w_L=config.get("writing", {}).get("w_L", 0.4),
            w_U=config.get("writing", {}).get("w_U", 0.4),
            w_A=config.get("writing", {}).get("w_A", 0.2),
        )
        self.theta = config.get("writing", {}).get("theta", 0.75)
        self.tau = config.get("writing", {}).get("tau", 0.6)
        self.delay = config.get("phase_delay_seconds", 5)
        self.max_calls = config.get("budget", {}).get("max_llm_calls_per_run", 20)
        self.max_tokens = config.get("budget", {}).get("max_tokens_per_call", 2500)
        self.max_retries_per_paragraph = config.get("writing", {}).get("max_retries_per_paragraph", 2)

    def select_model(self, eta: float) -> str:
        models = self.config.get("cloudflare_models", ["@cf/meta/llama-3.1-8b-instruct"])
        if eta >= self.tau and len(models) > 1:
            return models[0]
        return models[-1] if len(models) > 1 else models[0]

    def mark_sections(self, section_topics: List[str]) -> List[str]:
        indicators = []
        for topic in section_topics:
            eta = self.indicator.compute(topic, self.history)
            indicators.append((topic, eta))
        indicators.sort(key=lambda x: x[1], reverse=True)
        total_eta = sum(eta for _, eta in indicators)
        if total_eta == 0:
            return [t for t, _ in indicators[:2]]
        target = self.theta * total_eta
        marked = []
        cumulative = 0
        for topic, eta in indicators:
            marked.append(topic)
            cumulative += eta
            if cumulative >= target:
                break
        return marked

    def _get_relevant_concepts(self, topic: str, kb: Dict) -> List[Dict]:
        """Extract concepts relevant to a topic from the knowledge base dict."""
        concepts = kb.get("concepts", [])
        equations = kb.get("equations", [])
        procedures = kb.get("procedures", [])
        rules = kb.get("rules", [])
        
        topic_keywords = set(re.findall(r'\w+', topic.lower()))
        stop_words = {"the", "and", "of", "in", "to", "a", "for", "with", "on", "is", "method", "finite", "element"}
        topic_keywords -= stop_words
        
        all_items = []
        for c in concepts:
            all_items.append({"type": "concept", "data": c})
        for e in equations:
            all_items.append({"type": "equation", "data": e})
        for p in procedures:
            all_items.append({"type": "procedure", "data": p})
        for r in rules:
            all_items.append({"type": "rule", "data": r})
        
        scored = []
        for item in all_items:
            d = item["data"]
            text = ((d.get("name") or d.get("title") or d.get("rule") or "") + " " +
                    (d.get("explanation") or d.get("description") or "")).lower()
            text_words = set(re.findall(r'\w+', text))
            overlap = len(topic_keywords.intersection(text_words))
            scored.append((overlap, item))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        
        relevant = []
        for _, item in scored[:4]:
            d = item["data"]
            relevant.append({
                "type": item["type"],
                "name": d.get("name") or d.get("title") or d.get("rule", "Unknown"),
                "explanation": d.get("explanation") or d.get("description", ""),
                "math": d.get("mathematical_formulation") or d.get("latex", ""),
                "source_ids": d.get("source_ids", []),
            })
        return relevant

    def write_section(self, topic: str, kb: Dict, errors: List[str], document_map: List[Dict]) -> Optional[Dict]:
        eta = self.indicator.compute(topic, self.history)
        model = self.select_model(eta)
        print(f"    [DynamicWriter] Section: {topic}, eta={eta:.2f}, model={model}", file=sys.stderr)

        outline = self._generate_outline(topic, kb, model)
        if not outline:
            errors.append(f"Section '{topic}': outline generation failed")
            return None

        print(f"    [DynamicWriter] Outline: {len(outline)} paragraphs planned", file=sys.stderr)

        paragraphs = []
        for i, para_topic in enumerate(outline):
            if self.provider.total_calls >= self.max_calls:
                print(f"    [DynamicWriter] Budget exhausted at paragraph {i+1}", file=sys.stderr)
                break

            # FIX: Retry on rejection instead of silent drop
            para = None
            for retry in range(self.max_retries_per_paragraph):
                para = self._draft_paragraph(topic, para_topic, kb, model, i, len(outline), paragraphs, document_map)
                if para is not None:
                    break
                print(f"    [DynamicWriter] Paragraph {i+1} rejected (attempt {retry+1}), retrying with different angle", file=sys.stderr)
                time.sleep(1)
            
            if para:
                paragraphs.append(para)
            else:
                errors.append(f"Section '{topic}': paragraph {i+1} failed after {self.max_retries_per_paragraph} attempts")

        if not paragraphs:
            return None

        section = self._assemble_section(topic, paragraphs)
        is_valid = self._validate_section(section)

        if is_valid:
            self.history.record_clean_audit(topic)
            print(f"    [DynamicWriter] Section valid ({len(section.get('content', '').split())} words)", file=sys.stderr)
        else:
            self.history.record_failed_audit(topic)
            print(f"    [DynamicWriter] Section validation failed", file=sys.stderr)

        return section

    def _generate_outline(self, topic: str, kb: Dict, model: str) -> Optional[List[str]]:
        concepts = self._get_relevant_concepts(topic, kb)
        concept_names = [c["name"] for c in concepts[:6]]
        kb_display = kb_to_prompt_text(kb, max_chars=2000)

        outline_prompt = f"""Generate exactly 3 distinct paragraph topics for a section titled "{topic}".
Available concepts: {', '.join(concept_names)}
Knowledge base summary:
{kb_display}
Ensure the topics are mutually exclusive and do not overlap.
Return ONLY valid JSON: {{"outline": ["topic 1", "topic 2", "topic 3"]}}"""

        messages = [
            {"role": "system", "content": "You generate section outlines. Return ONLY valid JSON."},
            {"role": "user", "content": outline_prompt},
        ]
        result, error = self._call_llm(messages, model, temperature=0.3, max_tokens=500)
        if error or not result:
            return None
        if isinstance(result, dict) and "outline" in result:
            return result["outline"]
        if isinstance(result, list):
            return result
        return None

    def _draft_paragraph(self, section_topic, para_topic, kb, model, para_index, total_paras, previous_paragraphs, document_map) -> Optional[str]:
        concepts = self._get_relevant_concepts(para_topic + " " + section_topic, kb)
        
        allowed_sources: Set[str] = set()
        concepts_text = ""
        if concepts:
            for c in concepts:
                sources = ", ".join([f"[{sid}]" for sid in c.get("source_ids", [])])
                allowed_sources.update(c.get("source_ids", []))
                concepts_text += f"- {c['type'].upper()}: {c['name']}\n"
                concepts_text += f"  Fact: {c['explanation'][:300]}\n"
                if c.get("math"):
                    concepts_text += f"  Math: {c['math']}\n"
                concepts_text += f"  Allowed Citation: {sources}\n\n"
        else:
            concepts_text = "No specific concepts matched. Use general FEM knowledge.\n\n"

        previous_context = ""
        if previous_paragraphs:
            previous_context = "\nALREADY WRITTEN IN THIS SECTION (do NOT repeat):\n"
            for i, prev in enumerate(previous_paragraphs):
                previous_context += f"  Para {i+1}: {prev[:150]}...\n"

        doc_context = ""
        if document_map:
            doc_context = "\nPREVIOUS SECTIONS IN DOCUMENT:\n"
            for sec in document_map:
                doc_context += f"- {sec['title']}: {sec['summary']}\n"

        draft_prompt = f"""Write ONE academic paragraph (100-150 words) about: {para_topic}
Section: {section_topic}
{doc_context}
{previous_context}
Base your paragraph STRICTLY on these facts:
{concepts_text}
CRITICAL RULES:
1. CITATIONS: Only use these exact source IDs: {', '.join(sorted(allowed_sources))}
2. NO REPETITION: Do not repeat content from ALREADY WRITTEN paragraphs.
3. NO META-TEXT: Never start with "This chapter" or "This section".
4. Write ONLY the paragraph text. No JSON, no markdown, no title.
5. Use $math$ for inline equations."""

        messages = [
            {"role": "system", "content": "You are an academic writer. You strictly use provided citations. You never repeat previous text."},
            {"role": "user", "content": draft_prompt},
        ]

        result, error = self._call_llm(messages, model, temperature=0.4, max_tokens=800)
        if error:
            return None

        if isinstance(result, str):
            text = result.strip()
            
            # Repetition check
            for prev in previous_paragraphs:
                if calculate_word_overlap(text, prev) > 0.50:
                    return None  # Triggers retry
            
            # FIX: Safe citation stripping that preserves LaTeX math
            text = _strip_bad_citations(text, allowed_sources)
            
            # Strip meta-text
            text = re.sub(r'(?i)This (?:chapter|section|document|paragraph) (?:provides|discusses|explores|covers|outlines).*?\.\s*', '', text)
            text = re.sub(r'(?i)In this (?:chapter|section), we will.*?\.\s*', '', text)
            text = re.sub(r'\s+', ' ', text).strip()
            
            return text if len(text.split()) > 20 else None
        
        if isinstance(result, dict):
            return result.get("content", str(result))
        return str(result).strip() if result else None

    def _assemble_section(self, topic: str, paragraphs: List[str]) -> Dict:
        content = "\n\n".join(paragraphs)
        equations = _extract_equations(content)
        citations = _extract_citations(content)
        return {
            "title": topic,
            "content": content,
            "key_equations": sorted(set(equations))[:5],
            "citations_used": sorted(set(citations)),
        }

    def _validate_section(self, section: Dict) -> bool:
        if not section.get("title"):
            return False
        content = section.get("content", "")
        if len(content.split()) < 100:
            return False
        return True

    def _call_llm(self, messages, model, temperature=0.3, max_tokens=1000):
        """Pass model directly instead of mutating shared state."""
        text, error = self.provider.chat(messages, temperature, max_tokens, model=model)
        if error:
            return None, error
        if not text or not text.strip():
            return None, "Empty response"
        try:
            result = self.parser.parse(text, model_name=model)
            return result, None
        except Exception:
            return text, None

    def run(self, section_topics: List[str], kb: Dict, existing_sections: List[Dict], errors: List[str]) -> Tuple[List[Dict], int]:
        print("\n=== PHASE 3: DYNAMIC WRITE ===", file=sys.stderr)
        marked = self.mark_sections(section_topics)
        print(f"  Marked {len(marked)}/{len(section_topics)} sections: {marked}", file=sys.stderr)

        existing_titles = {s.get("title", "").lower(): i for i, s in enumerate(existing_sections)}
        all_sections = list(existing_sections)
        sections_written = 0
        
        document_map = []
        for sec in existing_sections:
            title = sec.get("title", "")
            content = sec.get("content", "")
            summary = content[:150].replace('\n', ' ') + "..." if len(content) > 150 else content.replace('\n', ' ')
            document_map.append({"title": title, "summary": summary})

        for topic in marked:
            if self.provider.total_calls >= self.max_calls:
                print(f"  Budget exhausted. Stopping.", file=sys.stderr)
                break
            print(f"  Writing: {topic}", file=sys.stderr)
            section = self.write_section(topic, kb, errors, document_map)
            if section:
                if topic.lower() in existing_titles:
                    all_sections[existing_titles[topic.lower()]] = section
                else:
                    all_sections.append(section)
                sections_written += 1
                content = section.get("content", "")
                summary = content[:150].replace('\n', ' ') + "..." if len(content) > 150 else content.replace('\n', ' ')
                document_map.append({"title": topic, "summary": summary})

        return all_sections, sections_written
