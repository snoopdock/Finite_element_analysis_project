#!/usr/bin/env python3
"""Writer orchestration for the Stage 2 decision policy."""

from __future__ import annotations

import re
from typing import List

from utils.text import load_json, save_json
from writing.policy_dynamic_writer import PolicyAwareDynamicWriter
from writing.corrective_rewriter import rewrite_paragraph
from analysis.policy_oaa_loop import PolicyAwareOAALoop
from analysis.document_semantic_review import review_document_claims
from analysis.semantic_feedback import attach_feedback


def _citation_ids(text: str) -> List[str]:
    result = []
    seen = set()
    for group in re.findall(r"\[([^\[\]\s,]+(?:\s*,\s*[^\[\]\s,]+)*)\]", str(text or "")):
        for value in group.split(","):
            value = value.strip()
            if value and value not in seen:
                seen.add(value)
                result.append(value)
    return result


def _replace_paragraph(section: dict, paragraph_index: int, replacement: str) -> dict | None:
    content = str(section.get("content", ""))
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
    if paragraph_index < 0 or paragraph_index >= len(paragraphs):
        return None
    paragraphs[paragraph_index] = replacement.strip()
    candidate = dict(section)
    candidate["content"] = "\n\n".join(paragraphs)
    candidate["status"] = "complete" if len(candidate["content"].split()) >= 100 else "incomplete"
    candidate["citations_used"] = _citation_ids(candidate["content"])
    return candidate


def phase_write_policy_aware(
    config,
    state,
    paths,
    provider,
    parser,
    errors,
    delay,
    budget,
    iteration_history,
    oaa_loop,
    section_topics: List[str],
    writing_indicator=None,
):
    """Run the write phase using the Stage 2 writer/OAA policies."""
    kb = state.get("knowledge_base", {})
    existing_sections = state.get("sections", [])

    writer = PolicyAwareDynamicWriter(
        provider,
        parser,
        config,
        iteration_history,
        writing_indicator=writing_indicator,
    )

    all_sections, sections_written = writer.run(
        section_topics,
        kb,
        existing_sections,
        errors,
    )

    state["last_writing_decisions"] = list(writer.last_decisions)

    semantic_config = config.get("semantic_verification", {})
    max_claims = int(semantic_config.get("max_claims_per_cycle", 0))
    evidence = load_json(paths["evidence"], [])
    if not isinstance(evidence, list):
        evidence = []

    review = {
        "enabled": False,
        "claims_checked": 0,
        "claims_supported": 0,
        "claims_contradicted": 0,
        "claims_insufficient": 0,
        "verification_skipped": True,
        "reports": [],
    }

    if semantic_config.get("enabled", False) and max_claims > 0:
        review = review_document_claims(
            all_sections,
            evidence,
            provider,
            parser,
            max_claims=max_claims,
            max_sources_per_claim=int(semantic_config.get("max_sources_per_claim", 2)),
            max_passages_per_source=int(semantic_config.get("max_passages_per_source", 2)),
            max_passage_chars=int(semantic_config.get("max_passage_chars", 1800)),
            max_tokens=int(semantic_config.get("max_tokens_per_claim", 700)),
            model=semantic_config.get("model"),
        )

    state["last_semantic_review"] = review
    all_sections = attach_feedback(all_sections, review)

    correction_enabled = bool(semantic_config.get("correction_enabled", False))
    max_rewrites = int(semantic_config.get("max_rewrites_per_cycle", 1))
    rewrite_jobs = []
    if correction_enabled and max_rewrites > 0:
        for report in review.get("reports", []):
            if not isinstance(report, dict):
                continue
            if str(report.get("judgment", "")).lower() == "contradicted":
                rewrite_jobs.append(report)
            if len(rewrite_jobs) >= max_rewrites:
                break

    correction_results = []
    if rewrite_jobs and not provider.budget_exhausted():
        for report in rewrite_jobs:
            section_id = str(report.get("section_id", ""))
            target = next(
                (
                    section for section in all_sections
                    if isinstance(section, dict)
                    and str(section.get("section_id", "")) == section_id
                ),
                None,
            )
            if target is None:
                continue

            result = rewrite_paragraph(
                {
                    "claim": report.get("claim", ""),
                    "reason": report.get("reason", ""),
                    "citation_ids": report.get("citation_ids", []),
                    "source_reports": report.get("sources", []),
                },
                provider,
                model=semantic_config.get("rewrite_model"),
                max_tokens=int(semantic_config.get("max_rewrite_tokens", 900)),
            )

            if not result.get("success"):
                correction_results.append({
                    "section_id": section_id,
                    "paragraph_index": report.get("paragraph_index"),
                    "action": "rewrite_rejected",
                    "error": result.get("error"),
                })
                continue

            candidate = _replace_paragraph(
                target,
                int(report.get("paragraph_index", -1)),
                result.get("text", ""),
            )
            if candidate is None:
                correction_results.append({
                    "section_id": section_id,
                    "paragraph_index": report.get("paragraph_index"),
                    "action": "rewrite_rejected",
                    "error": "Invalid paragraph index.",
                })
                continue

            reverification = review_document_claims(
                [candidate],
                evidence,
                provider,
                parser,
                max_claims=1,
                max_sources_per_claim=int(semantic_config.get("max_sources_per_claim", 2)),
                max_passages_per_source=int(semantic_config.get("max_passages_per_source", 2)),
                max_passage_chars=int(semantic_config.get("max_passage_chars", 1800)),
                max_tokens=int(semantic_config.get("max_tokens_per_claim", 700)),
                model=semantic_config.get("model"),
            )

            re_reports = reverification.get("reports", [])
            re_judgment = str(re_reports[0].get("judgment", "")) if re_reports else ""
            if re_judgment == "supported":
                for index, section in enumerate(all_sections):
                    if isinstance(section, dict) and str(section.get("section_id", "")) == section_id:
                        all_sections[index] = candidate
                        break
                correction_results.append({
                    "section_id": section_id,
                    "paragraph_index": report.get("paragraph_index"),
                    "action": "rewrite_accepted",
                    "reverification": reverification,
                })
            else:
                correction_results.append({
                    "section_id": section_id,
                    "paragraph_index": report.get("paragraph_index"),
                    "action": "rewrite_rejected",
                    "reverification": reverification,
                })

            break

    state["last_correction_results"] = correction_results
    state["last_semantic_feedback"] = {
        "sections": {
            str(section.get("section_id")): section.get("semantic_feedback", {})
            for section in all_sections
            if isinstance(section, dict)
            and section.get("section_id")
            and section.get("semantic_feedback")
        }
    }

    decision_oaa = PolicyAwareOAALoop(
        config,
        oaa_loop.section_splitter,
        oaa_loop.section_merger,
    )

    adjustment = decision_oaa.run(
        all_sections,
        iteration_history,
        kb,
    )

    oaa_loop.load_persisted_state(iteration_history)

    if adjustment:
        state["pending_adjustment"] = adjustment
        state["last_adjustment_decision"] = {
            "action": adjustment.get("action"),
            "section_id": adjustment.get("section_id"),
            "section_ids": list(adjustment.get("section_ids", [])),
            "reason": adjustment.get("reason", ""),
            "adjustment_score": dict(adjustment.get("adjustment_score", {})),
        }
    else:
        state.pop("pending_adjustment", None)
        state["last_adjustment_decision"] = None

    state["sections"] = all_sections
    save_json(paths["sections"], all_sections)

    return (
        all_sections,
        sections_written > 0,
        adjustment,
    )
