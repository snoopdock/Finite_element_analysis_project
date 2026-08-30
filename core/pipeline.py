#!/usr/bin/env python3
"""Core pipeline orchestration - phase sequencing only."""

import sys
from processing.llm_parser import LLMJSONParseError
from research.evidence import retrieve_evidence_parallel, merge_evidence, evidence_to_text, merge_knowledge
from processing.latex_builder import build_latex_document
from utils.text import load_json, save_json, save_text

EXTRACT_SYSTEM = """You are a senior computational mechanics researcher.
Extract detailed knowledge from provided sources about the Finite Element Method.
CRITICAL: Respond with ONLY valid JSON. No markdown code fences, no explanation.
Use double quotes for all keys and string values. No single quotes. No trailing commas.
Return this exact JSON structure:
{
  "concepts": [{"name": "Concept name", "explanation": "At least 4 sentences", "mathematical_formulation": "LaTeX or empty string", "source_ids": ["source_id"]}],
  "procedures": [{"step_number": 1, "title": "Step title", "description": "At least 4 sentences", "equations": ["LaTeX"], "source_ids": ["source_id"]}],
  "equations": [{"name": "Equation name", "latex": "Full LaTeX equation", "explanation": "Every term explained", "source_ids": ["source_id"]}],
  "rules": [{"rule": "Modeling rule", "explanation": "Why it matters", "source_ids": ["source_id"]}]
}"""

def call_llm_json(provider, parser, messages, temperature=0.2, max_tokens=2500, delay=5, max_retries=4):
    import time
    for attempt in range(max_retries):
        text, error = provider.chat(messages, temperature, max_tokens)
        if error:
            print(f"  [LLM] API error on attempt {attempt+1}: {error}", file=sys.stderr)
            time.sleep(delay)
            continue
        if not text or not isinstance(text, str) or not text.strip():
            print(f"  [LLM] Empty response on attempt {attempt+1}", file=sys.stderr)
            time.sleep(delay)
            continue
        try:
            obj = parser.parse(text, model_name="cloudflare")
            if isinstance(obj, list):
                if len(obj) > 0 and isinstance(obj[0], dict): obj = obj[0]
                else: time.sleep(delay); continue
            return obj, None
        except LLMJSONParseError as e:
            print(f"  [LLM] JSON parse failed on attempt {attempt+1}: {e.message}", file=sys.stderr)
            time.sleep(delay)
    return None, "Failed after all retries"

def validate_extraction(extraction):
    if not isinstance(extraction, dict): return False, None, "Not a dict"
    cleaned = {}
    for category in ["concepts", "procedures", "equations", "rules"]:
        items = extraction.get(category, [])
        if not isinstance(items, list): items = []
        valid_items = []
        for item in items:
            if not isinstance(item, dict): continue
            if "source_ids" not in item: item["source_ids"] = []
            elif not isinstance(item["source_ids"], list): item["source_ids"] = [item["source_ids"]]
            valid_items.append(item)
        cleaned[category] = valid_items
    return True, cleaned, None

def phase_research(config, state, paths, errors, gap_detector, provider=None, parser=None, skip_gap_analysis=False):
    print("\n=== PHASE 1: RESEARCH ===", file=sys.stderr)
    queries = list(config.get("seed_queries", ["finite element method"]))
    
    if not skip_gap_analysis and provider is not None and parser is not None:
        kb = state.get("knowledge_base", {})
        missing_topics, gap_queries = gap_detector.detect_gaps(knowledge_base=kb, provider=provider, parser=parser)
        if missing_topics:
            print(f"  [Gap Detection] {gap_detector.get_gap_report(missing_topics)}", file=sys.stderr)
            queries.extend(gap_queries)
        else:
            print(f"  [Gap Detection] No gaps detected", file=sys.stderr)
    else:
        print(f"  [Gap Detection] Skipped (converged or no provider)", file=sys.stderr)
    
    max_items = int(config.get("daily_limits", {}).get("max_evidence_items", 4))
    processed = set(state.get("processed_sources", []))
    old_evidence = load_json(paths["evidence"], [])
    old_ids = {e.get("source_id") for e in old_evidence if isinstance(e, dict)}
    
    new_evidence = retrieve_evidence_parallel(queries, max_items=max_items, max_workers=2)
    truly_new = [item for item in new_evidence if item.get("source_id") and item["source_id"] not in processed and item["source_id"] not in old_ids]
    
    all_evidence = merge_evidence(old_evidence, truly_new, max_keep=200)
    save_json(paths["evidence"], all_evidence)
    
    new_ids = {item.get("source_id") for item in truly_new if item.get("source_id")}
    state["processed_sources"] = sorted(list(processed | old_ids | new_ids))
    
    print(f"Found {len(truly_new)} new sources. Total: {len(all_evidence)}", file=sys.stderr)
    return all_evidence, len(truly_new) > 0

def phase_extract(config, state, paths, provider, parser, errors, delay, budget):
    print("\n=== PHASE 2: EXTRACT ===", file=sys.stderr)
    evidence = load_json(paths["evidence"], [])
    processed = set(state.get("processed_sources_extracted", []))
    unprocessed = [e for e in evidence if isinstance(e, dict) and e.get("source_id") not in processed]
    
    if not unprocessed:
        print("  No new sources to extract.", file=sys.stderr)
        return state.get("knowledge_base", {}), False
    
    if provider.total_calls >= budget.get("max_llm_calls_per_run", 20):
        print("  Budget exhausted. Skipping extract.", file=sys.stderr)
        return state.get("knowledge_base", {}), False
    
    max_context = int(config.get("limits", {}).get("max_evidence_context", 4))
    chars_per_source = int(config.get("limits", {}).get("chars_per_source", 1000))
    evidence_text = evidence_to_text(unprocessed, max_sources=max_context, chars_per_source=chars_per_source)
    
    extract_user = ("Topic: " + state.get("topic", "") + "\nObjective: " + state.get("objective", "") + "\n\nNEW evidence sources:\n" + evidence_text + "\n\nExtract DETAILED technical knowledge about FEM.")
    messages = [{"role": "system", "content": EXTRACT_SYSTEM}, {"role": "user", "content": extract_user}]
    
    max_tokens = budget.get("max_tokens_per_call", 2500)
    extraction, error = call_llm_json(provider, parser, messages, 0.2, max_tokens, delay)
    
    if error or extraction is None:
        errors.append(f"Extract error: {error}")
        return state.get("knowledge_base", {}), False
    
    is_valid, cleaned, validation_error = validate_extraction(extraction)
    if not is_valid:
        errors.append(f"Extract validation failed: {validation_error}")
        return state.get("knowledge_base", {}), False
    
    existing_kb = state.get("knowledge_base", {})
    updated_kb = merge_knowledge(existing_kb, cleaned)
    newly_extracted_ids = {e.get("source_id") for e in unprocessed if e.get("source_id")}
    state["processed_sources_extracted"] = sorted(list(processed | newly_extracted_ids))
    save_json(paths["research"], updated_kb)
    
    print(f"Knowledge base: {len(updated_kb.get('concepts', []))} concepts, {len(updated_kb.get('equations', []))} equations", file=sys.stderr)
    return updated_kb, True

def phase_write(config, state, paths, provider, parser, errors, delay, budget, iteration_history, oaa_loop, section_topics):
    """
    FIX: Accepts section_topics as the 11th argument instead of hardcoding it.
    This ensures dynamically split/merged sections are actually passed to the writer.
    """
    print("\n=== PHASE 3: WRITE (Dynamic) ===", file=sys.stderr)
    kb = state.get("knowledge_base", {})
    existing_sections = state.get("sections", [])
    
    from writing.dynamic_writer import DynamicWriter
    writer = DynamicWriter(provider, parser, config, iteration_history)
    
    # Use the unified section_topics passed from main.py
    all_sections, sections_written = writer.run(section_topics, kb, existing_sections, errors)
    
    adjustment = oaa_loop.run(all_sections, iteration_history, kb)
    
    if adjustment:
        print(f"  [OAA] Adjustment needed: {adjustment['action']}", file=sys.stderr)
        state["pending_adjustment"] = adjustment
    else:
        state.pop("pending_adjustment", None)
    
    state["sections"] = all_sections
    save_json(paths["sections"], all_sections)
    
    print(f"Phase 3 complete. {len(all_sections)} sections, {sections_written} written this cycle.", file=sys.stderr)
    return all_sections, sections_written > 0, adjustment

def phase_assemble(state, paths):
    print("\n=== PHASE 4: ASSEMBLE (no LLM) ===", file=sys.stderr)
    sections = state.get("sections", [])
    evidence = load_json(paths["evidence"], [])
    if not sections:
        print("  No sections to assemble.", file=sys.stderr)
        return False
    tex_content = build_latex_document(state, sections, evidence)
    save_text(paths["latex"], tex_content)
    print(f"LaTeX assembled. {len(sections)} sections.", file=sys.stderr)
    return True
