#!/usr/bin/env python3
"""Core research, extraction, writing, and assembly pipeline phases."""

from __future__ import annotations

import json
import pathlib
import sys
import time
from typing import Dict, List

from research.content_cache import cleanup_cache
from research.evidence import (
    evidence_to_text_section_aware,
    merge_evidence,
    merge_knowledge,
    confirm_sections_read,
    get_articles_needing_more_reading,
)
from research.reading_tracker import load_reading_state, save_reading_state
from utils.text import clean_text, kb_to_prompt_text, load_json, save_json, save_text
from processing.llm_parser import LLMJSONParseError

ROOT = pathlib.Path(__file__).resolve().parents[1]


def call_llm_json(
    provider,
    parser,
    messages,
    model=None,
    temperature=0.2,
    max_tokens=1000,
    max_retries=2,
    delay=1,
):
    """Call the LLM and parse a JSON response."""
    for attempt in range(max_retries):
        text, error = provider.chat(
            messages,
            temperature,
            max_tokens,
            model=model,
        )

        if error:
            print(
                f"  [LLM] API error on attempt {attempt + 1}: {error}",
                file=sys.stderr,
            )
            if attempt + 1 < max_retries:
                time.sleep(delay)
            continue

        if not text or not isinstance(text, str) or not text.strip():
            print(
                f"  [LLM] Empty response on attempt {attempt + 1}",
                file=sys.stderr,
            )
            if attempt + 1 < max_retries:
                time.sleep(delay)
            continue

        try:
            obj = parser.parse(text, model_name=model)
            if isinstance(obj, list):
                if len(obj) > 0 and isinstance(obj[0], dict):
                    obj = obj[0]
                else:
                    if attempt + 1 < max_retries:
                        time.sleep(delay)
                    continue

            if not isinstance(obj, dict):
                raise LLMJSONParseError("Parsed result is not a dictionary.")

            return obj, None

        except LLMJSONParseError as exc:
            print(
                f"  [LLM] JSON parse failed on attempt {attempt + 1}: "
                f"{getattr(exc, 'message', str(exc))}",
                file=sys.stderr,
            )
            if attempt + 1 < max_retries:
                time.sleep(delay)

        except Exception as exc:
            print(
                f"  [LLM] Parser error on attempt {attempt + 1}: {exc}",
                file=sys.stderr,
            )
            if attempt + 1 < max_retries:
                time.sleep(delay)

    return None, "Failed after all retries"


def _normalize_source_ids(source_ids):
    """Return a clean list of string source IDs."""
    if source_ids is None:
        return []

    if isinstance(source_ids, str):
        source_ids = [source_ids]

    if not isinstance(source_ids, list):
        return []

    cleaned = []
    seen = set()

    for source_id in source_ids:
        if not isinstance(source_id, str):
            continue
        source_id = source_id.strip()
        if not source_id or source_id in seen:
            continue
        seen.add(source_id)
        cleaned.append(source_id)

    return cleaned


def validate_extraction(extraction, allowed_source_ids=None):
    """Validate and normalize extraction structure."""
    if not isinstance(extraction, dict):
        return False, None, "Extraction is not a dictionary."

    if allowed_source_ids is None:
        allowed_source_ids = set()

    allowed_source_ids = set(str(x) for x in allowed_source_ids)

    cleaned = {
        "concepts": [],
        "procedures": [],
        "equations": [],
        "rules": [],
    }

    concepts = extraction.get("concepts", [])
    if not isinstance(concepts, list):
        concepts = []

    for item in concepts:
        if not isinstance(item, dict):
            continue

        name = item.get("name", "")
        explanation = item.get("explanation", "")
        if not isinstance(name, str):
            continue
        if not isinstance(explanation, str):
            explanation = str(explanation)

        name = name.strip()
        explanation = explanation.strip()
        if not name or not explanation:
            continue

        source_ids = [
            sid
            for sid in _normalize_source_ids(item.get("source_ids", []))
            if sid in allowed_source_ids
        ]
        if not source_ids:
            continue

        cleaned["concepts"].append(
            {
                "name": name,
                "explanation": explanation,
                "mathematical_formulation": str(
                    item.get("mathematical_formulation", "") or ""
                ),
                "source_ids": source_ids,
            }
        )

    procedures = extraction.get("procedures", [])
    if not isinstance(procedures, list):
        procedures = []

    for item in procedures:
        if not isinstance(item, dict):
            continue

        title = item.get("title", "")
        description = item.get("description", "")
        if not isinstance(title, str):
            continue
        if not isinstance(description, str):
            description = str(description)

        title = title.strip()
        description = description.strip()
        if not title or not description:
            continue

        source_ids = [
            sid
            for sid in _normalize_source_ids(item.get("source_ids", []))
            if sid in allowed_source_ids
        ]
        if not source_ids:
            continue

        equations = item.get("equations", [])
        if not isinstance(equations, list):
            equations = []

        equations = [
            str(value).strip()
            for value in equations
            if value is not None and str(value).strip()
        ]

        try:
            step_number = int(
                item.get(
                    "step_number",
                    len(cleaned["procedures"]) + 1,
                )
            )
        except (TypeError, ValueError):
            step_number = len(cleaned["procedures"]) + 1

        cleaned["procedures"].append(
            {
                "title": title,
                "description": description,
                "equations": equations,
                "step_number": step_number,
                "source_ids": source_ids,
            }
        )

    equations = extraction.get("equations", [])
    if not isinstance(equations, list):
        equations = []

    for item in equations:
        if not isinstance(item, dict):
            continue

        name = item.get("name", "")
        latex = item.get("latex", "")
        explanation = item.get("explanation", "")
        if not isinstance(name, str) or not isinstance(latex, str):
            continue
        if not isinstance(explanation, str):
            explanation = str(explanation)

        name = name.strip()
        latex = latex.strip()
        explanation = explanation.strip()
        if not name or not latex or not explanation:
            continue

        source_ids = [
            sid
            for sid in _normalize_source_ids(item.get("source_ids", []))
            if sid in allowed_source_ids
        ]
        if not source_ids:
            continue

        cleaned["equations"].append(
            {
                "name": name,
                "latex": latex,
                "explanation": explanation,
                "source_ids": source_ids,
            }
        )

    rules = extraction.get("rules", [])
    if not isinstance(rules, list):
        rules = []

    for item in rules:
        if not isinstance(item, dict):
            continue

        rule = item.get("rule", "")
        explanation = item.get("explanation", "")
        if not isinstance(rule, str):
            continue
        if not isinstance(explanation, str):
            explanation = str(explanation)

        rule = rule.strip()
        explanation = explanation.strip()
        if not rule or not explanation:
            continue

        source_ids = [
            sid
            for sid in _normalize_source_ids(item.get("source_ids", []))
            if sid in allowed_source_ids
        ]
        if not source_ids:
            continue

        cleaned["rules"].append(
            {
                "rule": rule,
                "explanation": explanation,
                "source_ids": source_ids,
            }
        )

    total_items = sum(len(cleaned[category]) for category in cleaned)
    if total_items == 0:
        return False, None, "Extraction contained no valid source-supported items."

    return True, cleaned, None


def phase_research(
    config,
    state,
    paths,
    errors,
    gap_detector,
    provider=None,
    parser=None,
    skip_gap_analysis=False,
):
    print("\n=== PHASE 1: RESEARCH ===", file=sys.stderr)

    queries = list(config.get("seed_queries", ["finite element method"]))

    if (
        not skip_gap_analysis
        and provider is not None
        and parser is not None
    ):
        kb = state.get("knowledge_base", {})

        try:
            missing_topics, gap_queries = gap_detector.detect_gaps(
                knowledge_base=kb,
                provider=provider,
                parser=parser,
            )
        except Exception as exc:
            errors.append(f"Gap detection error: {exc}")
            missing_topics = []
            gap_queries = []

        if missing_topics:
            print(
                "  [Gap Detection] "
                f"{gap_detector.get_gap_report(missing_topics)}",
                file=sys.stderr,
            )
            queries.extend(gap_queries)
        else:
            print(
                "  [Gap Detection] No gaps detected",
                file=sys.stderr,
            )
    else:
        print(
            "  [Gap Detection] Skipped (converged or no provider)",
            file=sys.stderr,
        )

    max_items = int(
        config.get("daily_limits", {}).get("max_evidence_items", 4)
    )

    processed = set(state.get("processed_sources", []))

    old_evidence = load_json(paths["evidence"], [])
    if not isinstance(old_evidence, list):
        old_evidence = []

    old_ids = {
        e.get("source_id")
        for e in old_evidence
        if isinstance(e, dict) and e.get("source_id")
    }

    try:
        retrieved_evidence = retrieve_evidence_parallel(
            queries,
            max_items=max_items,
            max_workers=2,
        )
    except Exception as exc:
        errors.append(f"Evidence retrieval error: {exc}")
        retrieved_evidence = []

    # Merge all retrieved records, not only previously unseen IDs. This is
    # essential for Stage 3 provenance: a source found again through a new
    # query/provider must retain that additional discovery context.
    all_evidence = merge_evidence(
        old_evidence,
        retrieved_evidence,
        max_keep=200,
    )

    save_json(
        paths["evidence"],
        all_evidence,
    )

    retrieved_ids = {
        item.get("source_id")
        for item in retrieved_evidence
        if isinstance(item, dict) and item.get("source_id")
    }
    new_ids = retrieved_ids - old_ids - processed

    state["processed_sources"] = sorted(
        processed | old_ids | retrieved_ids
    )

    print(
        f"Found {len(new_ids)} new sources. Total: {len(all_evidence)}",
        file=sys.stderr,
    )

    return all_evidence, bool(new_ids)


def phase_extract(
    config,
    state,
    paths,
    provider,
    parser,
    errors,
    delay,
    budget,
):
    print("\n=== PHASE 2: EXTRACT (Section-Aware) ===", file=sys.stderr)

    evidence = load_json(paths["evidence"], [])
    if not isinstance(evidence, list):
        evidence = []

    processed = set(state.get("processed_sources_extracted", []))

    reading_state = load_reading_state()

    unprocessed = [
        item
        for item in evidence
        if (
            isinstance(item, dict)
            and item.get("source_id")
            and item.get("source_id") not in processed
        )
    ]

    if not unprocessed:
        needs_more_reading = get_articles_needing_more_reading(
            evidence,
            reading_state,
        )

        if needs_more_reading:
            needed_ids = set(needs_more_reading)
            unprocessed = [
                item
                for item in evidence
                if (
                    isinstance(item, dict)
                    and item.get("source_id") in needed_ids
                )
            ]

            print(
                "  Found "
                f"{len(unprocessed)} sources with unread sections.",
                file=sys.stderr,
            )
        else:
            print(
                "  No new or unread sources to extract.",
                file=sys.stderr,
            )
            return state.get("knowledge_base", {}), False

    max_llm_calls = int(
        budget.get(
            "max_llm_calls_per_run",
            20,
        )
    )

    if provider.budget_exhausted():
        print("  Budget exhausted. Skipping extract.", file=sys.stderr)
        return state.get("knowledge_base", {}), False

    max_context = int(
        config.get("extract", {}).get(
            "max_context_chars",
            12000,
        )
    )

    sections_read_this_cycle = []
    updated_reading_state = reading_state
    evidence_text, updated_reading_state, sections_read = evidence_to_text_section_aware(
        evidence,
        reading_state,
        max_sources=int(config.get("extract", {}).get("max_sources", 4)),
        chars_per_source=int(config.get("extract", {}).get("chars_per_source", 3000)),
    )
    sections_read_this_cycle.extend(sections_read)

    evidence_text = evidence_text[:max_context]
    if not evidence_text:
        print("  No unread content available for extraction.", file=sys.stderr)
        return state.get("knowledge_base", {}), False

    selected_source_ids = {
        str(info["article_id"])
        for info in sections_read_this_cycle
        if isinstance(info, dict) and info.get("article_id")
    }

    if not selected_source_ids:
        print("  No source IDs were selected for extraction.", file=sys.stderr)
        return state.get("knowledge_base", {}), False

    extract_user = (
        "Topic: "
        + str(state.get("topic", ""))
        + "\nObjective: "
        + str(state.get("objective", ""))
        + "\n\nEvidence sources:\n"
        + evidence_text
        + "\n\n"
        "Extract detailed technical knowledge about the Finite Element Method."
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are a technical research extractor. "
                "Return ONLY valid JSON and cite only the supplied source IDs."
            ),
        },
        {
            "role": "user",
            "content": extract_user,
        },
    ]

    extraction, error = call_llm_json(
        provider,
        parser,
        messages,
        max_retries=2,
        delay=delay,
    )

    if error or extraction is None:
        errors.append(f"Extract error: {error}")
        return state.get("knowledge_base", {}), False

    is_valid, cleaned, validation_error = validate_extraction(
        extraction,
        allowed_source_ids=selected_source_ids,
    )

    if not is_valid:
        errors.append(f"Extract validation failed: {validation_error}")
        return state.get("knowledge_base", {}), False

    extracted_per_source = {}

    for category in (
        "concepts",
        "procedures",
        "equations",
        "rules",
    ):
        for item in cleaned.get(category, []):
            for sid in item.get("source_ids", []):
                if sid not in selected_source_ids:
                    continue
                extracted_per_source.setdefault(
                    sid,
                    {
                        "concepts": 0,
                        "equations": 0,
                        "procedures": 0,
                        "rules": 0,
                    },
                )
                extracted_per_source[sid][category] += 1

    if not extracted_per_source:
        errors.append(
            "Extraction succeeded syntactically but produced no source-supported knowledge."
        )
        return state.get("knowledge_base", {}), False

    reading_state = confirm_sections_read(
        sections_read_this_cycle,
        extracted_per_source,
        updated_reading_state,
    )

    save_reading_state(reading_state)

    processed |= selected_source_ids
    state["processed_sources_extracted"] = sorted(processed)

    existing_kb = state.get("knowledge_base", {})
    updated_kb = merge_knowledge(
        existing_kb,
        cleaned,
    )

    state["knowledge_base"] = updated_kb

    save_json(
        paths["research"],
        updated_kb,
    )

    cleanup_cache()

    print(
        "Knowledge base: "
        f"{len(updated_kb.get('concepts', []))} concepts, "
        f"{len(updated_kb.get('equations', []))} equations",
        file=sys.stderr,
    )

    return updated_kb, True


def phase_write(
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
    section_topics,
    writing_indicator=None,
):
    """Write phase with the dynamic writer."""
    print("\n=== PHASE 3: DYNAMIC WRITE ===", file=sys.stderr)

    kb = state.get("knowledge_base", {})
    existing_sections = state.get("sections", [])

    from writing.dynamic_writer import DynamicWriter

    writer = DynamicWriter(
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

    adjustment = oaa_loop.run(
        all_sections,
        iteration_history,
        kb,
    )

    if adjustment:
        print(
            "  [OAA] Adjustment needed: "
            f"{adjustment.get('action')}",
            file=sys.stderr,
        )
        state["pending_adjustment"] = adjustment
    else:
        state.pop("pending_adjustment", None)

    state["sections"] = all_sections

    save_json(paths["sections"], all_sections)

    return (
        all_sections,
        sections_written > 0,
        adjustment,
    )


def phase_assemble(state, paths):
    print("\n=== PHASE 4: ASSEMBLE (no LLM) ===", file=sys.stderr)

    sections = state.get("sections", [])
    evidence = load_json(paths["evidence"], [])

    if not sections:
        print("  No sections to assemble.", file=sys.stderr)
        return False

    tex_content = build_latex_document(
        state,
        sections,
        evidence,
    )

    save_text(
        paths["latex"],
        tex_content,
    )

    print(
        f"LaTeX assembled. {len(sections)} sections.",
        file=sys.stderr,
    )

    return True


def build_latex_document(state, sections, evidence):
    """Build the final LaTeX document from current state."""
    title = str(state.get("topic", "Finite Element Method"))
    lines = [
        "\\documentclass{article}",
        "\\usepackage{amsmath,amssymb}",
        "\\begin{document}",
        f"\\title{{{title}}}",
        "\\maketitle",
    ]

    for section in sections:
        if not isinstance(section, dict):
            continue
        section_title = str(section.get("title", "Untitled"))
        content = str(section.get("content", ""))
        lines.append(f"\\section{{{section_title}}}")
        lines.append(content)

    lines.append("\\end{document}")
    return "\n\n".join(lines)
