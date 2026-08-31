#!/usr/bin/env python3
"""Writer orchestration for the Stage 2 decision policy.

This module is a small compatibility layer around DynamicWriter. It keeps
phase sequencing unchanged while ensuring the same WritingIndicator instance
is shared by convergence and writing, and uses PolicyAwareDynamicWriter for
explicit section scheduling/model selection.
"""

from __future__ import annotations

from typing import List

from utils.text import save_json
from writing.policy_dynamic_writer import PolicyAwareDynamicWriter
from analysis.policy_oaa_loop import PolicyAwareOAALoop


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
    """Run the write phase using the Stage 2 writer/OAA decision policies."""
    kb = state.get(
        "knowledge_base",
        {},
    )

    existing_sections = state.get(
        "sections",
        [],
    )

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

    # Reuse the existing split/merge executors, but use an isolated
    # policy-aware OAA instance for anomaly/action prioritization. The
    # authoritative state remains in the caller's IterationHistory.
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

    if adjustment:
        state["pending_adjustment"] = adjustment
    else:
        state.pop(
            "pending_adjustment",
            None,
        )

    state["sections"] = all_sections

    save_json(
        paths["sections"],
        all_sections,
    )

    return (
        all_sections,
        sections_written > 0,
        adjustment,
    )
