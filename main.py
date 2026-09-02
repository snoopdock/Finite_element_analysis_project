#!/usr/bin/env python3
"""Main entry point for FEA pipeline."""

import argparse
import os
import pathlib
import sys
import traceback

from utils.text import (
    utcnow,
    ensure_base_dirs,
    load_yaml,
    load_json,
    save_json,
    save_text,
)
from core.state_manager import initialize_state, save_state
from core.budget import check_budget
from core.pipeline import (
    phase_research,
    phase_extract,
    phase_assemble,
)
from core.writer_orchestration import phase_write_policy_aware
from processing.llm_parser import UniversalLLMJSONParser
from providers.cloudflare import CloudflareProvider
from analysis.iteration_history import IterationHistory
from core.convergence import ConvergenceDetector
from analysis.gap_detector import GapDetector
from writing.section_splitter import SectionSplitter
from writing.section_merger import SectionMerger
from analysis.oaa_loop import OAALoop
from analysis.writing_indicator import WritingIndicator
from analysis.retrieval_event import create_retrieval_event
from core.retrieval_history_state import append_retrieval_event

from research.reading_tracker import load_reading_state
from research.evidence import get_reading_summary

ROOT = pathlib.Path(__file__).resolve().parent


def main():
    ensure_base_dirs(ROOT)

    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--config", default="config.yaml")
    args = arg_parser.parse_args()

    try:
        config_path = pathlib.Path(args.config)
        if not config_path.is_absolute():
            config_path = ROOT / config_path

        config = load_yaml(config_path)

        if not isinstance(config, dict):
            raise RuntimeError("Configuration file did not produce a dictionary.")

        paths = {
            "state": ROOT
            / config.get("state", {}).get(
                "path",
                "state/current_state.json",
            ),
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

        os.environ.setdefault(
            "FEA_MAX_LLM_CALLS",
            str(budget_config.get("max_llm_calls_per_run", 20)),
        )

        cache_config = config.get("cache", {})
        os.environ.setdefault(
            "FEA_CACHE_MAX_SIZE_MB",
            str(cache_config.get("max_size_mb", 500)),
        )

        account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
        api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()

        if not account_id:
            raise RuntimeError("CLOUDFLARE_ACCOUNT_ID is not set.")

        if not api_token:
            raise RuntimeError("CLOUDFLARE_API_TOKEN is not set.")

        llm_parser_instance = UniversalLLMJSONParser(
            enable_repair=False,
            repair_provider=None,
            verbose=True,
        )

        iteration_history = IterationHistory()

        if "iteration_history_data" in state:
            iteration_history.load_from_dict(
                state["iteration_history_data"]
            )

        convergence_detector = ConvergenceDetector(config)
        gap_detector = GapDetector(config)
        section_splitter = SectionSplitter(config)
        section_merger = SectionMerger(config)

        oaa_loop = OAALoop(
            config,
            section_splitter,
            section_merger,
        )
        oaa_loop.load_persisted_state(iteration_history)

        section_leverage = config.get("section_leverage", {})

        writing_indicator = WritingIndicator(
            w_L=config.get("writing", {}).get("w_L", 0.4),
            w_U=config.get("writing", {}).get("w_U", 0.4),
            w_A=config.get("writing", {}).get("w_A", 0.2),
            leverage_map=section_leverage if section_leverage else None,
        )

        print("\n=== BUDGET CHECK (Local) ===", file=sys.stderr)
        budget_config = check_budget(config)

        budget_msg = (
            f"Local limit: "
            f"{budget_config.get('max_llm_calls_per_run', 20)} calls"
        )

        state["last_budget_check"] = {
            "time": utcnow(),
            "type": "local",
            "message": budget_msg,
        }

        config_topics = config.get(
            "section_topics",
            [
                "Introduction and Scope of the Finite Element Method",
                "Mathematical Foundation: Strong Form, Weak Form, and Galerkin Method",
                "The Finite Element Procedure",
                "Rules for Modeling Physical Phenomena with FEM",
                "Verification, Validation, and Best Practices",
            ],
        )

        if not isinstance(config_topics, list):
            raise RuntimeError("section_topics must be a list.")

        existing_sections = state.get("sections", [])

        if not isinstance(existing_sections, list):
            existing_sections = []
            state["sections"] = existing_sections

        existing_titles = [
            s.get("title")
            for s in existing_sections
            if isinstance(s, dict) and s.get("title")
        ]

        section_topics = list(config_topics)

        for title in existing_titles:
            if title not in section_topics:
                section_topics.append(title)

        reading_state = load_reading_state()
        existing_evidence = load_json(
            paths["evidence"],
            [],
        )

        if not isinstance(existing_evidence, list):
            existing_evidence = []

        reading_summary = get_reading_summary(
            existing_evidence,
            reading_state,
        )

        recent_actions = []
        pending_adjustment = state.get("pending_adjustment")

        if isinstance(pending_adjustment, dict):
            action = pending_adjustment.get("action")
            if action:
                recent_actions.append(action)

        is_converged, convergence_diag = (
            convergence_detector.check_convergence(
                iteration_history,
                writing_indicator,
                section_topics,
                recent_actions,
                existing_sections,
                reading_summary,
            )
        )

        print("\n=== CONVERGENCE CHECK ===", file=sys.stderr)
        print(f"  Converged: {is_converged}", file=sys.stderr)
        print(
            f"  Reading coverage: "
            f"{reading_summary.get('reading_coverage_percent', 0.0):.2f}%",
            file=sys.stderr,
        )
        print(
            f"  Diagnostics: {convergence_diag}",
            file=sys.stderr,
        )

        models = config.get(
            "cloudflare_models",
            ["@cf/meta/llama-3.1-8b-instruct"],
        )

        max_tokens = budget_config.get(
            "max_tokens_per_call",
            2500,
        )

        provider = CloudflareProvider(
            account_id,
            api_token,
            models,
            max_tokens,
            max_logical_calls=int(
                budget_config.get(
                    "max_llm_calls_per_run",
                    20,
                )
            ),
        )

        print(f"\nModels: {models}", file=sys.stderr)
        print(
            f"Max tokens per call: {max_tokens}",
            file=sys.stderr,
        )
        print(
            "Max calls per run: "
            f"{budget_config.get('max_llm_calls_per_run', 20)}",
            file=sys.stderr,
        )

        print("\n" + "=" * 60, file=sys.stderr)
        print("STARTING FULL CYCLE", file=sys.stderr)
        print("=" * 60, file=sys.stderr)

        skip_gap = (
            is_converged
            and not state.get("pending_adjustment")
        )

        research_config = dict(config)
        pending_query_items = state.get("pending_evidence_queries", [])
        if not isinstance(pending_query_items, list):
            pending_query_items = []

        pending_queries = [
            str(item.get("query", "")).strip()
            for item in pending_query_items
            if isinstance(item, dict) and item.get("query")
        ]

        if pending_queries:
            base_queries = list(
                config.get(
                    "seed_queries",
                    [],
                )
            )
            normalized_pending = []
            seen_queries = set()
            for query in pending_queries + base_queries:
                query = str(query).strip()
                if not query or query.lower() in seen_queries:
                    continue
                seen_queries.add(query.lower())
                normalized_pending.append(query)
            research_config["seed_queries"] = normalized_pending

        evidence, new_sources = phase_research(
            research_config,
            state,
            paths,
            errors,
            gap_detector,
            provider,
            llm_parser_instance,
            skip_gap_analysis=skip_gap,
        )

        retrieval_report = state.get("retrieval_report", {})
        try:
            retrieval_event = create_retrieval_event(
                cycle=int(state.get("cycle", 0)),
                queries=None,
                report=retrieval_report,
            )
            if append_retrieval_event(state, retrieval_event):
                print(
                    "  [Retrieval History] Recorded retrieval event "
                    f"{retrieval_event['event_id']}",
                    file=sys.stderr,
                )
        except Exception as exc:
            errors.append(f"Retrieval history error: {exc}")

        if pending_query_items:
            state["last_correction_queries_used"] = pending_query_items
            state["pending_evidence_queries"] = []

        reading_state = load_reading_state()
        reading_summary = get_reading_summary(
            evidence,
            reading_state,
        )

        skip_write = convergence_detector.should_skip_write_phase(
            is_converged,
            new_sources,
        )

        sections = state.get("sections", [])
        kb = state.get("knowledge_base", {})
        extracted = False
        written = False
        adjustment = None

        if skip_write:
            print(
                "\n=== SKIPPING WRITE PHASE "
                "(Converged + No new sources) ===",
                file=sys.stderr,
            )
        else:
            processed_extracted = set(
                state.get(
                    "processed_sources_extracted",
                    [],
                )
            )

            unprocessed = [
                e
                for e in evidence
                if (
                    isinstance(e, dict)
                    and e.get("source_id")
                    and e.get("source_id")
                    not in processed_extracted
                )
            ]

            skip_extract = (
                convergence_detector.should_skip_extract_phase(
                    len(unprocessed)
                )
                and not state.get("pending_adjustment")
            )

            if skip_extract:
                print(
                    "\n=== SKIPPING EXTRACT PHASE "
                    "(No unprocessed sources) ===",
                    file=sys.stderr,
                )
            else:
                kb, extracted = phase_extract(
                    config,
                    state,
                    paths,
                    provider,
                    llm_parser_instance,
                    errors,
                    delay,
                    budget_config,
                )
                state["knowledge_base"] = kb

            sections, written, adjustment = phase_write_policy_aware(
                config,
                state,
                paths,
                provider,
                llm_parser_instance,
                errors,
                delay,
                budget_config,
                iteration_history,
                oaa_loop,
                section_topics,
                writing_indicator=writing_indicator,
            )

            state["sections"] = sections

            if adjustment:
                print(
                    f"\n=== EXECUTING ADJUSTMENT: "
                    f"{adjustment.get('action', 'unknown')} ===",
                    file=sys.stderr,
                )

                sections = oaa_loop.execute_adjustment(
                    adjustment,
                    sections,
                    provider,
                    llm_parser_instance,
                    iteration_history,
                )

                state["sections"] = sections

                save_json(
                    paths["sections"],
                    sections,
                )

                state.pop("pending_adjustment", None)
            else:
                state.pop("pending_adjustment", None)

        assembled = phase_assemble(
            state,
            paths,
        )

        state["cycle"] = int(
            state.get("cycle", 0)
        ) + 1

        state["iteration"] = int(
            state.get("iteration", 0)
        ) + 1

        state["last_run"] = utcnow()
        state["last_run_status"] = (
            "success"
            if not errors
            else "partial"
        )

        stats = provider.get_stats()
        state["model_usage"] = stats
        state["parser_stats"] = (
            llm_parser_instance.get_stats()
        )

        oaa_loop.save_persisted_state(
            iteration_history
        )

        state["iteration_history_data"] = (
            iteration_history.to_dict()
        )

        final_reading_state = load_reading_state()
        final_evidence = load_json(
            paths["evidence"],
            [],
        )

        if not isinstance(final_evidence, list):
            final_evidence = []

        final_reading_summary = get_reading_summary(
            final_evidence,
            final_reading_state,
        )

        convergence_diag["reading_coverage"] = (
            final_reading_summary.get(
                "reading_coverage_percent",
                0.0,
            )
        )

        state["convergence_diagnostics"] = convergence_diag

        save_state(
            paths,
            state,
        )

        report_lines = [
            "# FEA Pipeline - Cycle Report",
            "",
            f"**Time:** {utcnow()}",
            f"**Cycle:** {state.get('cycle', 0)}",
            f"**Total Iterations:** {state.get('iteration', 0)}",
            f"**Converged:** {is_converged}",
            "",
            "## Convergence Diagnostics",
            "",
            f"- Eta variance: {convergence_diag.get('eta_variance')}",
            f"- Invariant violations: {convergence_diag.get('invariant_violations')}",
            f"- Adjust actions: {convergence_diag.get('adjust_actions')}",
            f"- Incomplete sections: {convergence_diag.get('incomplete_sections')}",
            f"- Unstable sections: {convergence_diag.get('unstable_sections')}",
            f"- Reading coverage: {convergence_diag.get('reading_coverage', 0.0):.2f}%",
            "",
            "## This Cycle",
            "",
            f"- Correction queries used: {len(pending_query_items)}",
            f"- New sources found: {new_sources}",
            f"- Extracted: {extracted}",
            f"- Sections written: {written}",
            f"- Adjustment executed: {adjustment.get('action') if adjustment else 'none'}",
            f"- Write phase skipped: {skip_write}",
            f"- LaTeX assembled: {assembled}",
            "",
        ]

        if errors:
            report_lines.append("## Errors")
            report_lines.append("")
            for error in errors:
                report_lines.append(f"- {error}")
        else:
            report_lines.extend(
                [
                    "## Status: SUCCESS",
                    "",
                ]
            )

        save_text(
            paths["report"],
            "\n".join(report_lines),
        )

        print("\n" + "=" * 60, file=sys.stderr)
        print(
            f"CYCLE COMPLETE. "
            f"Iterations: {state.get('iteration', 0)}",
            file=sys.stderr,
        )
        print("=" * 60 + "\n", file=sys.stderr)

    except Exception:
        error_text = traceback.format_exc()

        save_text(
            ROOT / "output" / "error.txt",
            error_text,
        )

        print(
            error_text,
            file=sys.stderr,
        )

        sys.exit(1)


if __name__ == "__main__":
    main()
