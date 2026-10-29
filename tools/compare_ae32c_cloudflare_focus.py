#!/usr/bin/env python3
"""Offline comparison of a focused Cloudflare investigation with historical trials."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any


def load_comparisons(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    found: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(root.rglob("comparison.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("provider") == "cloudflare":
            found.append((path, data))
    return found


def summarize(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    graph = data.get("graph_assisted", {})
    graph = graph if isinstance(graph, dict) else {}
    report = graph.get("report", {})
    report = report if isinstance(report, dict) else {}
    summary = graph.get("summary", {})
    summary = summary if isinstance(summary, dict) else {}
    coverage = report.get("required_source_coverage", {})
    coverage = coverage if isinstance(coverage, dict) else {}
    budget = report.get("budget", {})
    budget = budget if isinstance(budget, dict) else {}
    metrics = data.get("comparison_metrics", {})
    metrics = metrics if isinstance(metrics, dict) else {}

    reads: list[dict[str, Any]] = []
    for call in report.get("tool_calls", []) if isinstance(report.get("tool_calls"), list) else []:
        if not isinstance(call, dict) or call.get("tool") != "read_source_file":
            continue
        args = call.get("arguments", {})
        args = args if isinstance(args, dict) else {}
        reads.append({
            "path": args.get("path") if isinstance(args.get("path"), str) else "unknown",
            "status": call.get("status") if isinstance(call.get("status"), str) else "unknown",
            "evidence_id": call.get("evidence_id") if isinstance(call.get("evidence_id"), str) else None,
        })

    reasons: Counter[str] = Counter()
    events: Counter[str] = Counter()
    for event in report.get("errors", []) if isinstance(report.get("errors"), list) else []:
        if not isinstance(event, dict):
            continue
        name = event.get("event")
        if isinstance(name, str):
            events[name] += 1
        for reason in event.get("reason_codes", []) if isinstance(event.get("reason_codes"), list) else []:
            if isinstance(reason, str):
                reasons[reason] += 1
        if name in {"model_action_rejected", "finalization_recovery_budget_exhausted"}:
            for key in ("reason_code", "reason"):
                reason = event.get(key)
                if isinstance(reason, str):
                    reasons[reason] += 1

    report_status = report.get("status", summary.get("status"))
    stop_reason = report.get("stop_reason", summary.get("stop_reason"))
    coverage_status = coverage.get("status", summary.get("required_source_coverage_status"))
    return {
        "evaluation_id": data.get("evaluation_id"),
        "provider": data.get("provider"),
        "model": data.get("model"),
        "source_revision": data.get("source_revision"),
        "source_revision_status": data.get("source_revision_status"),
        "runner_revision": data.get("runner_revision"),
        "runner_revision_status": data.get("runner_revision_status"),
        "revision_attestation": data.get("revision_attestation"),
        "graph_status": report_status,
        "stop_reason": stop_reason,
        "required_source_coverage_status": coverage_status,
        "required_paths": coverage.get("required_paths", []),
        "complete_read_paths": coverage.get("complete_read_paths", []),
        "direct_read_paths": coverage.get("direct_read_paths", []),
        "missing_complete_reads": coverage.get("missing_complete_reads", []),
        "root_cause_direct_citation_paths": coverage.get("root_cause_direct_citation_paths", []),
        "missing_root_cause_direct_citations": coverage.get(
            "missing_root_cause_direct_citations",
            summary.get("required_source_missing_root_citations", []),
        ),
        "source_read_calls": reads,
        "successful_source_read_calls": sum(item["status"] == "ok" for item in reads),
        "source_reference_count": metrics.get("graph_assisted_source_reference_count", summary.get("source_reference_count")),
        "graph_elapsed_seconds": metrics.get("graph_assisted_elapsed_seconds"),
        "graph_reported_tokens": metrics.get("graph_assisted_reported_tokens"),
        "final_citation_validation": summary.get("final_citation_validation"),
        "source_textual_support_status": summary.get("source_textual_support_status"),
        "finalization_rejections_used": budget.get("finalization_rejections_used"),
        "finalization_rounds_used": budget.get("finalization_rounds_used"),
        "finalization_recovery_budget_exhausted_events": events.get("finalization_recovery_budget_exhausted", 0),
        "required_source_read_reminders": events.get("required_source_read_reminder", 0),
        "final_diagnosis_rejections": events.get("final_diagnosis_rejected", 0),
        "model_action_rejections": events.get("model_action_rejected", 0),
        "rejection_reason_counts": dict(sorted(reasons.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-root", required=True, type=Path)
    parser.add_argument("--current-root", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-markdown", required=True, type=Path)
    args = parser.parse_args()

    baseline_files = load_comparisons(args.baseline_root)
    current_files = load_comparisons(args.current_root)
    if not baseline_files:
        raise SystemExit("No Cloudflare comparison.json files found in historical artifact.")
    if not current_files:
        raise SystemExit("No Cloudflare comparison.json found for focused run.")

    baseline = [summarize(path, data) for path, data in baseline_files]
    current = summarize(*current_files[-1])
    baseline_models = sorted({str(item["model"]) for item in baseline if item.get("model")})
    model_changed = bool(current.get("model") and baseline_models and current["model"] not in baseline_models)

    complete = sum(item["required_source_coverage_status"] == "complete" for item in baseline)
    exhausted = sum(item["stop_reason"] == "finalization_recovery_budget_exhausted" for item in baseline)
    missing = Counter(path for item in baseline for path in item["missing_complete_reads"] if isinstance(path, str))
    reasons: Counter[str] = Counter()
    for item in baseline:
        reasons.update(item["rejection_reason_counts"])
    elapsed = [item["graph_elapsed_seconds"] for item in baseline if isinstance(item["graph_elapsed_seconds"], (int, float))]
    tokens = [item["graph_reported_tokens"] for item in baseline if isinstance(item["graph_reported_tokens"], (int, float))]

    payload = {
        "schema_version": "ae32c/cloudflare-focused-comparison/v2",
        "interpretation": "Operational comparison only; diagnostic correctness is not assessed.",
        "model_comparison": {
            "historical_models": baseline_models,
            "current_model": current.get("model"),
            "model_changed_from_historical_trials": model_changed,
            "paired_experiment": False,
            "note": "If model differs, this is an exploratory model-change observation, not an apples-to-apples causal comparison.",
        },
        "historical_baseline": {
            "trial_count": len(baseline),
            "models": baseline_models,
            "graph_completed_count": sum(item["graph_status"] == "completed" for item in baseline),
            "source_coverage_complete_count": complete,
            "finalization_recovery_exhausted_count": exhausted,
            "missing_complete_read_path_counts": dict(sorted(missing.items())),
            "rejection_reason_counts": dict(sorted(reasons.items())),
            "mean_graph_elapsed_seconds": round(mean(elapsed), 3) if elapsed else None,
            "mean_graph_reported_tokens": round(mean(tokens), 1) if tokens else None,
            "trials": baseline,
        },
        "focused_current_run": current,
        "execution_provenance": {
            "source_revision": current.get("source_revision"),
            "source_revision_status": current.get("source_revision_status"),
            "runner_revision": current.get("runner_revision"),
            "runner_revision_status": current.get("runner_revision_status"),
            "revision_attestation": current.get("revision_attestation"),
        },
        "comparison": {
            "historical_source_coverage_complete": f"{complete}/{len(baseline)}",
            "current_source_coverage_complete": current["required_source_coverage_status"] == "complete",
            "historical_finalization_exhausted": f"{exhausted}/{len(baseline)}",
            "current_finalization_exhausted": current["stop_reason"] == "finalization_recovery_budget_exhausted",
            "historical_mean_graph_elapsed_seconds": round(mean(elapsed), 3) if elapsed else None,
            "current_graph_elapsed_seconds": current["graph_elapsed_seconds"],
            "historical_mean_graph_reported_tokens": round(mean(tokens), 1) if tokens else None,
            "current_graph_reported_tokens": current["graph_reported_tokens"],
        },
        "limitations": [
            "One focused run is a debugging observation, not a statistical comparison.",
            "Historical trials and the focused run are not a randomized paired experiment.",
            "If model differs, outcome differences cannot be attributed to the model alone without further controlled repetitions.",
            "Source coverage and resolved citations do not establish causal correctness.",
            "Provider/model output requires independent review against frozen ground truth.",
        ],
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# AE-32C focused Cloudflare comparison",
        "",
        "**Interpretation:** operational comparison only; diagnostic correctness remains unassessed.",
        "",
        "## Model identity and comparability",
        "",
        f"- Historical model(s): `{', '.join(baseline_models) or 'not reported'}`",
        f"- Current model: `{current.get('model') or 'not reported'}`",
        f"- Model changed from historical trials: `{model_changed}`",
        "- This is not a paired experiment. If the model changed, treat the result as an exploratory observation, not proof that the model caused any improvement.",
        "",
        "## Historical Cloudflare trials",
        "",
        f"- Trials: {len(baseline)}",
        f"- Graph investigations completed: {payload['historical_baseline']['graph_completed_count']}/{len(baseline)}",
        f"- Required source coverage complete: {complete}/{len(baseline)}",
        f"- Finalization recovery exhausted: {exhausted}/{len(baseline)}",
        f"- Mean graph elapsed seconds: {payload['historical_baseline']['mean_graph_elapsed_seconds']}",
        f"- Mean graph reported tokens: {payload['historical_baseline']['mean_graph_reported_tokens']}",
        "",
        "### Historical rejection reasons",
        "",
    ]
    lines.extend([f"- `{key}`: {value}" for key, value in sorted(reasons.items())] or ["- None recorded."])
    lines += [
        "",
        "## Focused current run",
        "",
        f"- Evaluation ID: `{current.get('evaluation_id')}`",
        f"- Source revision: `{current.get('source_revision')}` (`{current.get('source_revision_status')}`)",
        f"- Runner revision: `{current.get('runner_revision')}` (`{current.get('runner_revision_status')}`)",
        f"- Model: `{current.get('model')}`",
        f"- Graph status: `{current['graph_status']}`",
        f"- Stop reason: `{current['stop_reason']}`",
        f"- Required source coverage: `{current['required_source_coverage_status']}`",
        f"- Complete source paths: `{', '.join(current['complete_read_paths']) or 'none'}`",
        f"- Missing complete reads: `{', '.join(current['missing_complete_reads']) or 'none'}`",
        f"- Missing direct root-cause citations: `{', '.join(current['missing_root_cause_direct_citations']) or 'none'}`",
        f"- Successful source-read calls: `{current['successful_source_read_calls']}`",
        f"- Model action rejections: `{current['model_action_rejections']}`",
        f"- Citation validation: `{current['final_citation_validation']}`",
        f"- Textual source support: `{current['source_textual_support_status']}`",
        f"- Finalization recovery exhausted: `{current['stop_reason'] == 'finalization_recovery_budget_exhausted'}`",
        f"- Graph elapsed seconds: `{current['graph_elapsed_seconds']}`",
        f"- Graph reported tokens: `{current['graph_reported_tokens']}`",
        "",
        "### Current rejection reasons",
        "",
    ]
    lines.extend([f"- `{key}`: {value}" for key, value in sorted(current["rejection_reason_counts"].items())] or ["- None recorded."])
    lines += [
        "",
        "## Interpretation guide",
        "",
        "- Incomplete source coverage: inspect deterministic prefetch/read results before changing prompts.",
        "- Complete reads but missing direct citations: inspect whether the model used the evidence it already received; do not weaken citation gates.",
        "- `tool_action_shape_invalid`: inspect the required action schema and compare model compliance across controlled trials.",
        "- Complete coverage and resolved citations still require independent adjudication of the diagnosis.",
        "",
    ]
    args.output_markdown.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {args.output_json}")
    print(f"Wrote {args.output_markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
