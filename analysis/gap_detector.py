#!/usr/bin/env python3
"""Gap Detector - Two-step dynamic gap identification."""

import re
import sys
import time
from typing import Dict, List, Optional, Tuple, Set

import requests

DEFAULT_USER_AGENT = (
    "FEA_Pipeline_Bot/1.0 "
    "(https://github.com/snoopdock/Finite_element_analysis_project; "
    "automated research bot)"
)


class GapDetector:
    def __init__(self, config: Dict):
        gap_config = config.get("gap_detection", {})
        self.max_wikipedia_topics = gap_config.get("max_wikipedia_topics", 30)
        self.max_gap_queries = gap_config.get("max_gap_queries_per_cycle", 3)
        self.min_concept_coverage = gap_config.get("min_concepts_per_topic", 2)
        self.wikipedia_pages = gap_config.get("wikipedia_pages", [
            "Finite element method",
            "Weak formulation",
            "Galerkin method",
            "Structural mechanics",
        ])
        self.wiki_cache: List[str] = []
        self.last_fetch_time: float = 0
        self.cache_ttl = 3600

    def fetch_wikipedia_taxonomy(self) -> List[str]:
        if self.wiki_cache and (time.time() - self.last_fetch_time) < self.cache_ttl:
            print(f"  [GapDetector] Using cached taxonomy ({len(self.wiki_cache)} topics)",
                  file=sys.stderr)
            return self.wiki_cache

        print("  [GapDetector] Step 1: Fetching Wikipedia taxonomy...", file=sys.stderr)
        all_topics: Set[str] = set()

        for page_title in self.wikipedia_pages:
            try:
                topics = self._fetch_page_sections(page_title)
                all_topics.update(topics)
                time.sleep(0.5)
            except Exception as e:
                print(f"  [GapDetector] Warning: Failed '{page_title}': {e}",
                      file=sys.stderr)
                continue

        try:
            related = self._fetch_related_topics("Finite element method")
            all_topics.update(related)
        except Exception:
            pass

        cleaned_topics = []
        for topic in all_topics:
            cleaned = self._clean_topic(topic)
            if cleaned and 3 < len(cleaned) < 100:
                cleaned_topics.append(cleaned)

        cleaned_topics = list(set(cleaned_topics))[:self.max_wikipedia_topics]
        self.wiki_cache = cleaned_topics
        self.last_fetch_time = time.time()

        print(f"  [GapDetector] Step 1 complete: {len(cleaned_topics)} topics",
              file=sys.stderr)
        return cleaned_topics

    def _fetch_page_sections(self, page_title: str) -> List[str]:
        url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "parse",
            "page": page_title,
            "format": "json",
            "prop": "sections",
        }
        headers = {"User-Agent": DEFAULT_USER_AGENT}
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        sections = data.get("parse", {}).get("sections", [])
        topics = []
        for section in sections:
            title = section.get("line", "")
            level = int(section.get("toclevel", 1))
            if level <= 3 and title:
                topics.append(title)
        return topics

    def _fetch_related_topics(self, page_title: str) -> List[str]:
        url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "titles": page_title,
            "format": "json",
            "prop": "links",
            "pllimit": 50,
            "plnamespace": 0,
        }
        headers = {"User-Agent": DEFAULT_USER_AGENT}
        # FIX #6: Actually pass headers to the request
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        pages = data.get("query", {}).get("pages", {})
        topics = []
        for page_id, page_data in pages.items():
            links = page_data.get("links", [])
            for link in links[:20]:
                title = link.get("title", "")
                if self._is_fem_related(title):
                    topics.append(title)
        return topics

    def _is_fem_related(self, title: str) -> bool:
        fem_keywords = {
            "finite element", "mesh", "element", "node", "stiffness",
            "weak form", "galerkin", "variational", "pde", "partial differential",
            "boundary condition", "shape function", "basis function",
            "discretization", "numerical method", "interpolation",
            "quadrature", "integration", "assembly", "dof", "degree of freedom",
            "convergence", "error estimate", "adaptive", "refinement",
            "nonlinear", "dynamic", "transient", "modal", "eigenvalue",
            "heat transfer", "fluid", "structural", "mechanics",
            "elasticity", "plasticity", "viscoelastic", "composite",
            "plate", "shell", "beam", "truss", "frame",
            "multiphysics", "coupling", "contact", "fracture",
        }
        title_lower = title.lower()
        return any(keyword in title_lower for keyword in fem_keywords)

    def _clean_topic(self, topic: str) -> str:
        topic = re.sub(r'<[^>]+>', '', topic)
        topic = re.sub(r'\[edit\]', '', topic)
        topic = re.sub(r'\[\d+\]', '', topic)
        topic = re.sub(r'&amp;', '&', topic)
        topic = re.sub(r'&lt;', '<', topic)
        topic = re.sub(r'&gt;', '>', topic)
        topic = re.sub(r'\s+', ' ', topic).strip()
        return topic

    def analyze_gaps_with_llm(self, taxonomy, knowledge_base, provider, parser):
        print("  [GapDetector] Step 2: LLM gap analysis...", file=sys.stderr)
        kb_summary = self._summarize_knowledge_base(knowledge_base)
        taxonomy_str = "\n".join(f"  - {topic}" for topic in taxonomy[:25])

        prompt = (
            f"You are a senior FEM researcher performing a gap analysis.\n\n"
            f"Standard FEM taxonomy (from Wikipedia):\n{taxonomy_str}\n\n"
            f"Our current knowledge base:\n{kb_summary}\n\n"
            f"Identify which important FEM topics are MISSING.\n"
            f"Return at most {self.max_gap_queries} missing topics.\n\n"
            f"Return ONLY valid JSON:\n"
            f'{{"missing_topics": [{{"topic": "name", "importance": "high/medium/low", '
            f'"search_query": "query", "reason": "why"}}]}}'
        )

        messages = [
            {"role": "system", "content": "You are a gap analysis expert. Return ONLY valid JSON."},
            {"role": "user", "content": prompt},
        ]

        text, error = provider.chat(messages, temperature=0.2, max_tokens=1500)
        if error or not text:
            print(f"  [GapDetector] LLM gap analysis failed: {error}", file=sys.stderr)
            return [], []

        try:
            result = parser.parse(text, model_name="cloudflare")
        except Exception as e:
            print(f"  [GapDetector] Parse failed: {e}", file=sys.stderr)
            return [], []

        missing_topics = []
        search_queries = []

        if isinstance(result, dict) and "missing_topics" in result:
            for item in result["missing_topics"][:self.max_gap_queries]:
                if isinstance(item, dict):
                    topic = item.get("topic", "")
                    query = item.get("search_query", "")
                    importance = item.get("importance", "medium")
                    if topic and importance in ("high", "medium"):
                        missing_topics.append(topic)
                        search_queries.append(query or f"finite element method {topic}")

        print(f"  [GapDetector] Step 2 complete: {len(missing_topics)} gaps", file=sys.stderr)
        for i, topic in enumerate(missing_topics):
            print(f"    Gap {i+1}: {topic}", file=sys.stderr)

        return missing_topics, search_queries

    def detect_gaps(self, knowledge_base, provider=None, parser=None):
        taxonomy = self.fetch_wikipedia_taxonomy()
        if not taxonomy:
            return [], []
        if provider is not None and parser is not None:
            return self.analyze_gaps_with_llm(taxonomy, knowledge_base, provider, parser)
        return self._keyword_fallback(taxonomy, knowledge_base)

    def _summarize_knowledge_base(self, kb: Dict) -> str:
        lines = []
        for category in ["concepts", "procedures", "equations", "rules"]:
            items = kb.get(category, [])
            if items:
                names = [i.get("name") or i.get("title") or i.get("rule", "?")
                         for i in items[:10]]
                lines.append(f"{category.capitalize()} ({len(items)}): {', '.join(names)}")
        return "\n".join(lines) if lines else "Knowledge base is empty."

    def _keyword_fallback(self, taxonomy, knowledge_base):
        kb_text = self._extract_kb_text(knowledge_base).lower()
        missing, queries = [], []
        for topic in taxonomy[:10]:
            keywords = topic.lower().split()
            matches = sum(1 for kw in keywords if kw in kb_text)
            if matches / max(len(keywords), 1) < 0.5:
                missing.append(topic)
                queries.append(f"finite element method {topic}")
        return missing[:self.max_gap_queries], queries[:self.max_gap_queries]

    def _extract_kb_text(self, kb: Dict) -> str:
        texts = []
        for category in ["concepts", "procedures", "equations", "rules"]:
            for item in kb.get(category, []):
                if isinstance(item, dict):
                    name = item.get("name") or item.get("title") or item.get("rule", "")
                    explanation = item.get("explanation") or item.get("description", "")
                    texts.append(f"{name} {explanation}")
        return " ".join(texts)

    def get_gap_report(self, missing_topics: List[str]) -> str:
        if not missing_topics:
            return "No gaps detected."
        lines = [f"Detected {len(missing_topics)} gaps:"]
        for topic in missing_topics[:10]:
            lines.append(f"  - {topic}")
        return "\n".join(lines)
