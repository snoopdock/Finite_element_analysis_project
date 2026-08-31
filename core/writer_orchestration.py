#!/usr/bin/env python3
"""Writer orchestration for the Stage 2 decision policy."""

from __future__ import annotations

from typing import List

from utils.text import load_json, save_json
from writing.policy_dynamic_writer import PolicyAwareDynamicWriter
from analysis.policy_oaa_loop import PolicyAwareOAALoop
from analysis.document_semantic_review import review_document_claims


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

    if semantic_config.get("enabled", False) and max_claims > 0:
        evidence = load_json(paths["evidence"], [])
        if not isinstance(evidence, list):
            evidence = []

        state["last_semantic_review"] = review_document_claims(
            all_sections,
            evidence,
            provider,
            parser,
            max_claims=max_claims,
            max_sources_per_claim=int(
                semantic_config.get("max_sources_per_claim", 2)
            ),
            max_passages_per_source=int(
                semantic_config.get("max_passages_per_source", 2)
            ),
            max_passage_chars=int(
                semantic_config.get("max_passage_chars", 1800)
            ),
            max_tokens=int(
                semantic_config.get("max_tokens_per_claim", 700)
            ),
            model=semantic_config.get("model"),
        )
    else:
        state["last_semantic_review"] = {
            "enabled": False,
            "claims_checked": 0,
            "claims_supported": 0,
            "claims_contradicted": 0,
            "claims_insufficient": 0,
            "verification_skipped": True,
            "reports": [],
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
