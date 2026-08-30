#!/usr/bin/env python3
"""Convergence detection based on document state and evidence coverage."""

from __future__ import annotations

import json
import pathlib
import statistics
from typing import Dict, List, Tuple

from core.section_identity import ensure_section_id
from analysis.citation_validator import validate_document_citations

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ConvergenceDetector:
    def __init__(self, config: Dict):
        convergence_config = config.get("convergence", {})
        self.m = max(1, int(convergence_config.get("window", 3)))
        self.epsilon = float(convergence_config.get("eta_variance_threshold", 0.1))
        self.min_words_per_section = int(convergence_config.get("min_words_per_section", 150))
        self.minimum_reading_coverage = float(convergence_config.get("minimum_reading_coverage_percent", 80.0))
        self.minimum_citation_coverage = float(convergence_config.get("minimum_citation_coverage_percent", 80.0))

        configured_path = pathlib.Path(convergence_config.get("evidence_path", "output/evidence.json"))
        self.evidence_path = configured_path if configured_path.is_absolute() else ROOT / configured_path
        self.consecutive_convergence = 0

    @staticmethod
    def _section_for_topic(topic: str, sections: List[Dict]):
        topic_lower = str(topic).strip().lower()
        for section in sections:
            if not isinstance(section, dict):
                continue
            if str(section.get("title", "")).strip().lower() == topic_lower:
                ensure_section_id(section)
                return section
        return None

    def _load_persisted_evidence(self) -> List[Dict]:
        try:
            with open(self.evidence_path, "r", encoding="utf-8") as handle:
                evidence = json.load(handle)
            return evidence if isinstance(evidence, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def check_convergence(self, iteration_history, writing_indicator, section_topics: List[str], recent_actions: List[str], sections: List[Dict] = None, reading_summary: Dict = None, evidence: List[Dict] = None) -> Tuple[bool, Dict]:
        sections = sections or []
        recent_actions = recent_actions or []
        if evidence is None:
            evidence = self._load_persisted_evidence()

        diagnostics = {
            "eta_variance": None,
            "invariant_violations": 0,
            "adjust_actions": len(recent_actions),
            "consecutive_clean_cycles": self.consecutive_convergence,
            "incomplete_sections": 0,
            "unstable_sections": 0,
            "reading_coverage": 0.0,
            "citation_coverage": 0.0,
            "invalid_citation_sections": 0,
            "converged": False,
            "reasons": [],
        }

        eta_values = []
        for topic in section_topics:
            if not topic:
                continue
            section = self._section_for_topic(topic, sections)
            target = section if section is not None else topic
            eta_values.append(float(writing_indicator.compute(target, iteration_history)))

        variance = statistics.variance(eta_values) if len(eta_values) > 1 else 0.0
        diagnostics["eta_variance"] = variance

        recent_failures = 0
        unstable_sections = 0
        for topic in section_topics:
            if not topic:
                continue
            section = self._section_for_topic(topic, sections)
            if section is not None:
                history_key = section.get("section_id")
            elif hasattr(iteration_history, "resolve_section_key"):
                history_key = iteration_history.resolve_section_key(topic)
            else:
                history_key = topic

            audits = iteration_history.audits.get(history_key, [])
            if not audits:
                unstable_sections += 1
                continue

            recent = audits[-self.m:]
            recent_failures += sum(1 for audit in recent if not bool(audit))
            if len(audits) < self.m or not all(bool(audit) for audit in recent):
                unstable_sections += 1

        diagnostics["invariant_violations"] = recent_failures
        diagnostics["unstable_sections"] = unstable_sections

        incomplete_sections = 0
        for section in sections:
            if not isinstance(section, dict):
                incomplete_sections += 1
                continue
            content = section.get("content", "")
            content = content if isinstance(content, str) else str(content)
            status = section.get("status", "")
            if len(content.split()) < self.min_words_per_section or status in {"needs_generation", "needs_rewrite", "needs_expansion", "incomplete"}:
                incomplete_sections += 1
        diagnostics["incomplete_sections"] = incomplete_sections

        reading_coverage = float((reading_summary or {}).get("reading_coverage_percent", 0.0))
        diagnostics["reading_coverage"] = reading_coverage

        citation_summary = validate_document_citations(sections, evidence)
        citation_coverage = float(citation_summary.get("citation_coverage_percent", 0.0))
        diagnostics["citation_coverage"] = citation_coverage
        diagnostics["invalid_citation_sections"] = len(citation_summary.get("invalid_sections", []))

        conditions = {
            "variance_ok": variance < self.epsilon,
            "no_violations": recent_failures == 0,
            "no_actions": len(recent_actions) == 0,
            "all_sections_stable": unstable_sections == 0,
            "all_sections_complete": incomplete_sections == 0,
            "sufficient_reading": reading_coverage >= self.minimum_reading_coverage,
            "sufficient_citations": citation_summary.get("valid", False) and citation_coverage >= self.minimum_citation_coverage,
        }

        if not evidence:
            conditions["sufficient_citations"] = True
            diagnostics["reasons"].append("citation_evidence_unavailable")

        for name, passed in conditions.items():
            if not passed:
                diagnostics["reasons"].append(name)

        is_converged = all(conditions.values())
        self.consecutive_convergence = self.consecutive_convergence + 1 if is_converged else 0
        diagnostics["consecutive_clean_cycles"] = self.consecutive_convergence
        diagnostics["converged"] = is_converged
        return is_converged, diagnostics

    def should_skip_write_phase(self, is_converged: bool, new_sources_found: bool) -> bool:
        return bool(is_converged and not new_sources_found)

    def should_skip_extract_phase(self, unprocessed_sources: int) -> bool:
        return int(unprocessed_sources) <= 0
