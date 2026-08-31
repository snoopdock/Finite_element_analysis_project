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
from analysis.correction_planner import plan_corrections


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

    correction_plan = {
        "evidence_queries": [],
        "rewrite_jobs": [],
        "query_count": 0,
        "rewrite_count": 0,
    }
    correction_enabled = bool(semantic_config.get("correction_enabled", False))
    if correction_enabled and review.get("reports"):
        correction_plan = plan_corrections(
            review,
            max_queries=int(semantic_config.get("max_evidence_queries_per_cycle", 2)),
            max_rewrites=int(semantic_config.get("max_rewrites_per_cycle", 1)),
        )

    pending = state.get("pending_evidence_queries", [])
    if not isinstance(pending, list):
        pending = []
    existing_query_keys = {
        str(item.get("query", "")).strip().lower()
        for item in pending
        if isinstance(item, dict) and item.get("query")
    }
    for item in correction_plan.get("evidence_queries", []):
        if not isinstance(item, dict):
            continue
        query = str(item.get("query", "")).strip()
        if not query or query.lower() in existing_query_keys:
            continue
        pending.append(item)
        existing_query_keys.add(query.lower())
    max_pending_queries = int(semantic_config.get("max_pending_evidence_queries", 8))
    state["pending_evidence_queries"] = pending[-max(0, max_pending_queries):]
    state["last_correction_plan"] = correction_plan

    correction_results = []
    rewrite_jobs = correction_plan.get("rewrite_jobs", [])
    if correction_enabled and rewrite_jobs and not provider.budget_exhausted():
        for job in rewrite_jobs[:max(0, int(semantic_config.get("max_rewrites_per_cycle", 1)))]:
            section_id = str(job.get("section_id", ""))
            target_index = next(
                (
                    index for index, section in enumerate(all_sections)
                    if isinstance(section, dict)
                    and str(section.get("section_id", "")) == section_id
                ),
                None,
            )
            if target_index is None:
                continue

            result = rewrite_paragraph(
                job,
                provider,
                model=semantic_config.get("rewrite_model"),
                max_tokens=int(semantic_config.get("max_rewrite_tokens", 900)),
            )
            if not result.get("success"):
                correction_results.append({"section_id": section_id, "action": "rewrite_rejected", "error": result.get("error")})
                continue

            paragraph_index = int(job.get("paragraph_index", -1))
            candidate = _replace_paragraph(all_sections[target_index], paragraph_index, result.get("text", ""))
            if candidate is None:
                correction_results.append({"section_id": section_id, "action": "rewrite_rejected", "error": "Invalid paragraph index."})
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
                candidate.pop("semantic_feedback", None)
                candidate["semantic_feedback"] = {
                    "action": "retain",
                    "severity": "low",
                    "confidence": float(re_reports[0].get("confidence", 0.0)),
                    "judgments": ["supported"],
                    "claims_checked": 1,
                    "reverified": True,
                    "reverification_reason": str(re_reports[0].get("reason", "")),
                    "reverified_sources": [
                        str(value) for value in re_reports[0].get("citation_ids", []) if value
                    ],
                    "reverification": reverification,
                }
                all_sections[target_index] = candidate
                correction_results.append({"section_id": section_id, "action": "rewrite_accepted", "reverification": reverification})
            else:
                correction_results.append({"section_id": section_id, "action": "rewrite_rejected", "reverification": reverification})
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
