#!/usr/bin/env python3
"""Offline comparison of one focused Cloudflare run against historical trials."""
from __future__ import annotations
import argparse, json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any


def load_comparisons(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    found = []
    for path in sorted(root.rglob("comparison.json")):
        try: data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError): continue
        if isinstance(data, dict) and data.get("provider") == "cloudflare": found.append((path, data))
    return found


def summarize(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    graph = data.get("graph_assisted", {}); report = graph.get("report", {}) if isinstance(graph, dict) else {}
    report = report if isinstance(report, dict) else {}
    coverage = report.get("required_source_coverage", {}); coverage = coverage if isinstance(coverage, dict) else {}
    budget = report.get("budget", {}); budget = budget if isinstance(budget, dict) else {}
    metrics = data.get("comparison_metrics", {}); metrics = metrics if isinstance(metrics, dict) else {}
    reads = []
    for call in report.get("tool_calls", []) if isinstance(report.get("tool_calls"), list) else []:
        if isinstance(call, dict) and call.get("tool") == "read_source_file":
            args = call.get("arguments", {}); args = args if isinstance(args, dict) else {}
            reads.append({"path": args.get("path") if isinstance(args.get("path"), str) else "unknown",
                          "status": call.get("status") if isinstance(call.get("status"), str) else "unknown",
                          "evidence_id": call.get("evidence_id") if isinstance(call.get("evidence_id"), str) else None})
    reasons: Counter[str] = Counter(); events: Counter[str] = Counter()
    for event in report.get("errors", []) if isinstance(report.get("errors"), list) else []:
        if not isinstance(event, dict): continue
        name = event.get("event")
        if isinstance(name, str): events[name] += 1
        for reason in event.get("reason_codes", []) if isinstance(event.get("reason_codes"), list) else []:
            if isinstance(reason, str): reasons[reason] += 1
        if name in {"model_action_rejected", "finalization_recovery_budget_exhausted"}:
            for key in ("reason_code", "reason"):
                reason = event.get(key)
                if isinstance(reason, str): reasons[reason] += 1
    return {
        "evaluation_id": data.get("evaluation_id"), "graph_status": report.get("status"),
        "stop_reason": report.get("stop_reason"), "required_source_coverage_status": coverage.get("status"),
        "required_paths": coverage.get("required_paths", []), "complete_read_paths": coverage.get("complete_read_paths", []),
        "direct_read_paths": coverage.get("direct_read_paths", []), "missing_complete_reads": coverage.get("missing_complete_reads", []),
        "missing_root_cause_direct_citations": coverage.get("missing_root_cause_direct_citations", []),
        "source_read_calls": reads, "successful_source_read_calls": sum(x["status"] == "ok" for x in reads),
        "graph_elapsed_seconds": metrics.get("graph_assisted_elapsed_seconds"),
        "graph_reported_tokens": metrics.get("graph_assisted_reported_tokens"),
        "source_reference_count": metrics.get("graph_assisted_source_reference_count"),
        "finalization_rejections_used": budget.get("finalization_rejections_used"),
        "finalization_rounds_used": budget.get("finalization_rounds_used"),
        "finalization_recovery_budget_exhausted_events": events.get("finalization_recovery_budget_exhausted", 0),
        "required_source_read_reminders": events.get("required_source_read_reminder", 0),
        "final_diagnosis_rejections": events.get("final_diagnosis_rejected", 0),
        "rejection_reason_counts": dict(sorted(reasons.items())),
    }


def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("--baseline-root", required=True, type=Path); p.add_argument("--current-root", required=True, type=Path)
    p.add_argument("--output-json", required=True, type=Path); p.add_argument("--output-markdown", required=True, type=Path); args = p.parse_args()
    baseline_files = load_comparisons(args.baseline_root); current_files = load_comparisons(args.current_root)
    if not baseline_files: raise SystemExit("No Cloudflare comparison.json files found in historical artifact.")
    if not current_files: raise SystemExit("No Cloudflare comparison.json found for focused run.")
    baseline = [summarize(path, data) for path, data in baseline_files]; current = summarize(*current_files[-1])
    complete = sum(x["required_source_coverage_status"] == "complete" for x in baseline)
    exhausted = sum(x["stop_reason"] == "finalization_recovery_budget_exhausted" for x in baseline)
    missing = Counter(path for x in baseline for path in x["missing_complete_reads"] if isinstance(path, str))
    reasons: Counter[str] = Counter()
    for x in baseline: reasons.update(x["rejection_reason_counts"])
    elapsed = [x["graph_elapsed_seconds"] for x in baseline if isinstance(x["graph_elapsed_seconds"], (int, float))]
    tokens = [x["graph_reported_tokens"] for x in baseline if isinstance(x["graph_reported_tokens"], (int, float))]
    payload = {
        "schema_version": "ae32c/cloudflare-focused-comparison/v1", "interpretation": "Operational comparison only; diagnostic correctness is not assessed.",
        "historical_baseline": {"trial_count": len(baseline), "graph_completed_count": sum(x["graph_status"] == "completed" for x in baseline),
            "source_coverage_complete_count": complete, "finalization_recovery_exhausted_count": exhausted,
            "missing_complete_read_path_counts": dict(sorted(missing.items())), "rejection_reason_counts": dict(sorted(reasons.items())),
            "mean_graph_elapsed_seconds": round(mean(elapsed), 3) if elapsed else None, "mean_graph_reported_tokens": round(mean(tokens), 1) if tokens else None, "trials": baseline},
        "focused_current_run": current,
        "comparison": {"historical_source_coverage_complete": f"{complete}/{len(baseline)}", "current_source_coverage_complete": current["required_source_coverage_status"] == "complete",
            "historical_finalization_exhausted": f"{exhausted}/{len(baseline)}", "current_finalization_exhausted": current["stop_reason"] == "finalization_recovery_budget_exhausted",
            "historical_mean_graph_elapsed_seconds": round(mean(elapsed), 3) if elapsed else None, "current_graph_elapsed_seconds": current["graph_elapsed_seconds"],
            "historical_mean_graph_reported_tokens": round(mean(tokens), 1) if tokens else None, "current_graph_reported_tokens": current["graph_reported_tokens"]},
        "limitations": ["One focused run is a debugging observation, not a statistical comparison.", "Historical four-trial results and this focused run are not a randomized paired experiment.", "Source coverage and resolved citations do not establish causal correctness.", "Provider/model output still requires independent review against frozen ground truth."]}
    args.output_json.parent.mkdir(parents=True, exist_ok=True); args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    lines = ["# AE-32C focused Cloudflare comparison", "", "**Operational comparison only; diagnostic correctness remains unassessed.**", "",
        "## Historical Cloudflare trials", "", f"- Trials: {len(baseline)}", f"- Graph investigations completed: {payload['historical_baseline']['graph_completed_count']}/{len(baseline)}",
        f"- Required source coverage complete: {complete}/{len(baseline)}", f"- Finalization recovery exhausted: {exhausted}/{len(baseline)}",
        f"- Mean graph elapsed seconds: {payload['historical_baseline']['mean_graph_elapsed_seconds']}", f"- Mean graph reported tokens: {payload['historical_baseline']['mean_graph_reported_tokens']}", "", "### Historical rejection reasons", ""]
    lines.extend([f"- `{k}`: {v}" for k,v in sorted(reasons.items())] or ["- None recorded."])
    lines += ["", "## Focused current run", "", f"- Graph status: `{current['graph_status']}`", f"- Stop reason: `{current['stop_reason']}`",
        f"- Required source coverage: `{current['required_source_coverage_status']}`", f"- Complete source paths: `{', '.join(current['complete_read_paths']) or 'none'}`",
        f"- Missing complete reads: `{', '.join(current['missing_complete_reads']) or 'none'}`", f"- Missing direct root-cause citations: `{', '.join(current['missing_root_cause_direct_citations']) or 'none'}`",
        f"- Successful source-read calls: `{current['successful_source_read_calls']}`", f"- Finalization rejections used: `{current['finalization_rejections_used']}`",
        f"- Finalization budget exhausted: `{current['stop_reason'] == 'finalization_recovery_budget_exhausted'}`", f"- Graph elapsed seconds: `{current['graph_elapsed_seconds']}`",
        f"- Graph reported tokens: `{current['graph_reported_tokens']}`", "", "### Current rejection reasons", ""]
    lines.extend([f"- `{k}`: {v}" for k,v in sorted(current["rejection_reason_counts"].items())] or ["- None recorded."])
    lines += ["", "## Interpretation", "", "- Incomplete source coverage: inspect deterministic prefetch/read results before changing prompts.",
        "- Complete coverage but `source_reference_evidence_id_unbound`: inspect ledger binding and exact path/line/hash checks.",
        "- If operational gates pass, preserve artifacts and send the diagnosis for independent review; do not claim correctness.",
        "- One focused run is not a provider ranking or statistically conclusive improvement.", ""]
    args.output_markdown.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {args.output_json}"); print(f"Wrote {args.output_markdown}"); return 0

if __name__ == "__main__": raise SystemExit(main())
