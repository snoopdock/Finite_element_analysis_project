#!/usr/bin/env python3
"""Main entry point for FEA pipeline."""

import argparse
import os
import pathlib
import sys
import traceback

from utils.text import utcnow, ensure_base_dirs, load_yaml, load_json, save_json, save_text
from core.state_manager import initialize_state, save_state
from core.budget import check_budget
from core.pipeline import phase_research, phase_extract, phase_write, phase_assemble
from processing.llm_parser import UniversalLLMJSONParser
from providers.cloudflare import CloudflareProvider
from analysis.iteration_history import IterationHistory
from core.convergence import ConvergenceDetector
from analysis.gap_detector import GapDetector
from writing.section_splitter import SectionSplitter
from writing.section_merger import SectionMerger
from analysis.oaa_loop import OAALoop
from analysis.writing_indicator import WritingIndicator

ROOT = pathlib.Path(__file__).resolve().parent


def main():
    ensure_base_dirs(ROOT)
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--config", default="config.yaml")
    args = arg_parser.parse_args()

    try:
        config = load_yaml(args.config)
        paths = {
            "state": ROOT / config.get("state", {}).get("path", "state/current_state.json"),
            "evidence": ROOT / "output" / "evidence.json",
            "research": ROOT / "output" / "research.json",
            "sections": ROOT / "output" / "sections.json",
            "latex": ROOT / "output" / "guideline.tex",
            "report": ROOT / "output" / "validation_report.md",
        }

        state = initialize_state(paths, config)
        errors = []
        delay = int(config.get("phase_delay_seconds", 5))
        budget_config = config.get("budget", {})

        account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
        api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()

        if not account_id:
            raise RuntimeError("CLOUDFLARE_ACCOUNT_ID is not set.")
        if not api_token:
            raise RuntimeError("CLOUDFLARE_API_TOKEN is not set.")

        llm_parser_instance = UniversalLLMJSONParser(enable_repair=False, repair_provider=None, verbose=True)

        iteration_history = IterationHistory()
        if "iteration_history_data" in state:
            iteration_history.load_from_dict(state["iteration_history_data"])

        convergence_detector = ConvergenceDetector(config)
        gap_detector = GapDetector(config)
        section_splitter = SectionSplitter(config)
        section_merger = SectionMerger(config)
        oaa_loop = OAALoop(config, section_splitter, section_merger)

        # Build leverage map from config
        section_leverage = config.get("section_leverage", {})
        writing_indicator = WritingIndicator(
            w_L=config.get("writing", {}).get("w_L", 0.4),
            w_U=config.get("writing", {}).get("w_U", 0.4),
            w_A=config.get("writing", {}).get("w_A", 0.2),
            leverage_map=section_leverage if section_leverage else None,
        )

        print("\n=== BUDGET CHECK (Local) ===", file=sys.stderr)
        budget_config = check_budget(config)
        budget_msg = f"Local limit: {budget_config.get('max_llm_calls_per_run', 20)} calls"
        state["last_budget_check"] = {"time": utcnow(), "type": "local", "message": budget_msg}

        # Unified section_topics (config + existing dynamic sections)
        config_topics = config.get("section_topics", [
            "Introduction and Scope of the Finite Element Method",
            "Mathematical Foundation: Strong Form, Weak Form, and Galerkin Method",
            "The Finite Element Procedure",
            "Rules for Modeling Physical Phenomena with FEM",
            "Verification, Validation, and Best Practices",
        ])
        existing_sections = state.get("sections", [])
        existing_titles = [s.get("title") for s in existing_sections if s.get("title")]

        section_topics = list(config_topics)
        for title in existing_titles:
            if title not in section_topics:
                section_topics.append(title)

        recent_actions = [state.get("pending_adjustment", {}).get("action")] if state.get("pending_adjustment") else []

        # Pass existing_sections for completeness check
        is_converged, convergence_diag = convergence_detector.check_convergence(
            iteration_history, writing_indicator, section_topics, recent_actions, existing_sections
        )

        print(f"\n=== CONVERGENCE CHECK ===", file=sys.stderr)
        print(f"  Converged: {is_converged}", file=sys.stderr)
        print(f"  Diagnostics: {convergence_diag}", file=sys.stderr)

        models = config.get("cloudflare_models", ["@cf/meta/llama-3.1-8b-instruct"])
        max_tokens = budget_config.get("max_tokens_per_call", 2500)
        provider = CloudflareProvider(account_id, api_token, models, max_tokens)

        print(f"\nModels: {models}", file=sys.stderr)
        print(f"Max tokens per call: {max_tokens}", file=sys.stderr)
        print(f"Max calls per run: {budget_config.get('max_llm_calls_per_run', 10)}", file=sys.stderr)
        print("\n" + "="*60, file=sys.stderr)
        print("STARTING FULL CYCLE", file=sys.stderr)
        print("="*60, file=sys.stderr)

        skip_gap = is_converged and not state.get("pending_adjustment")
        evidence, new_sources = phase_research(config, state, paths, errors, gap_detector, provider, llm_parser_instance, skip_gap_analysis=skip_gap)

        skip_write = convergence_detector.should_skip_write_phase(is_converged, new_sources)

        if skip_write:
            print("\n=== SKIPPING WRITE PHASE (Converged + No new sources) ===", file=sys.stderr)
            kb = state.get("knowledge_base", {})
            extracted = False
            sections = state.get("sections", [])
            written = False
            adjustment = None
        else:
            unprocessed = [
                e for e in evidence
                if isinstance(e, dict) and e.get("source_id") not in set(state.get("processed_sources_extracted", []))
            ]
            skip_extract = convergence_detector.should_skip_extract_phase(len(unprocessed))

            if skip_extract:
                print("\n=== SKIPPING EXTRACT PHASE (No unprocessed sources) ===", file=sys.stderr)
                kb = state.get("knowledge_base", {})
                extracted = False
            else:
                kb, extracted = phase_extract(config, state, paths, provider, llm_parser_instance, errors, delay, budget_config)
                state["knowledge_base"] = kb

            sections, written, adjustment = phase_write(config, state, paths, provider, llm_parser_instance, errors, delay, budget_config, iteration_history, oaa_loop, section_topics)

            if adjustment:
                print(f"\n=== EXECUTING ADJUSTMENT: {adjustment['action']} ===", file=sys.stderr)
                sections = oaa_loop.execute_adjustment(adjustment, sections, provider, llm_parser_instance, iteration_history)
                state["sections"] = sections
                save_json(paths["sections"], sections)

        assembled = phase_assemble(state, paths)

        state["cycle"] = int(state.get("cycle", 0)) + 1
        state["iteration"] = int(state.get("iteration", 0)) + 1
        state["last_run"] = utcnow()
        state["last_run_status"] = "success" if not errors else "partial"
        state["model_usage"] = provider.get_stats() if not skip_write else state.get("model_usage", {})
        state["parser_stats"] = llm_parser_instance.get_stats()
        state["iteration_history_data"] = iteration_history.to_dict()
        state["convergence_diagnostics"] = convergence_diag

        save_state(paths, state)

        # Generate report
        kb = state.get("knowledge_base", {})
        stats = provider.get_stats() if not skip_write else state.get("model_usage", {})

        report_lines = [
            "# FEA Pipeline - Cycle Report", "",
            f"**Time:** {utcnow()}",
            f"**Cycle:** {state.get('cycle', 0)}",
            f"**Total Iterations:** {state.get('iteration', 0)}",
            f"**Converged:** {is_converged}", "",
            "## Convergence Diagnostics",
            f"- Eta variance: {convergence_diag.get('eta_variance')}",
            f"- Invariant violations: {convergence_diag.get('invariant_violations')}",
            f"- Adjust actions: {convergence_diag.get('adjust_actions')}",
            f"- Incomplete sections: {convergence_diag.get('incomplete_sections')}", "",
            "## This Cycle",
            f"- New sources found: {new_sources}",
            f"- Sections written: {written}",
            f"- Adjustment executed: {adjustment['action'] if adjustment else 'none'}",
            f"- Write phase skipped: {skip_write}", "",
        ]

        if errors:
            report_lines.append("## Errors")
            for e in errors:
                report_lines.append(f"- {e}")
        else:
            report_lines.append("## Status: SUCCESS")

        save_text(paths["report"], "\n".join(report_lines))

        print("\n" + "="*60, file=sys.stderr)
        print(f"CYCLE COMPLETE. Iterations: {state.get('iteration', 0)}", file=sys.stderr)
        print("="*60 + "\n", file=sys.stderr)

    except Exception:
        error_text = traceback.format_exc()
        save_text(ROOT / "output" / "error.txt", error_text)
        print(error_text, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
