#!/usr/bin/env python3
"""Aggregate AE-32C graph-utilization telemetry from published comparison.json files."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import uuid
from typing import Any

from audit_engine.semantic_audit.ae32c.graph_utilization import (
    aggregate_graph_utilization_runs,
    summarize_graph_utilization_assessment,
)

MAX_INPUT_BYTES = 25_000_000
MAX_INPUT_FILES = 100


def _load_comparison(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("input_must_be_regular_non_symlink_file")
    size = path.stat().st_size
    if size <= 0 or size > MAX_INPUT_BYTES:
        raise ValueError("input_size_out_of_range")
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != "ae32c/evaluation-comparison/v1":
        raise ValueError("unsupported_comparison_schema")
    evaluation_id = value.get("evaluation_id")
    if not isinstance(evaluation_id, str) or re.fullmatch(r"ae32c-eval-[0-9a-f]{32}", evaluation_id) is None:
        raise ValueError("invalid_evaluation_id")
    graph = value.get("graph_assisted")
    if not isinstance(graph, dict):
        graph = {}
    report = graph.get("report")
    summary = graph.get("summary")
    assessment = report.get("graph_utilization_assessment") if isinstance(report, dict) else None
    if not isinstance(assessment, dict) and isinstance(summary, dict):
        assessment = summary.get("graph_utilization_assessment")
    compact = summarize_graph_utilization_assessment(assessment)
    metrics = value.get("comparison_metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    comparison_values = {}
    for key in (
        "baseline_reported_tokens", "graph_assisted_reported_tokens",
        "baseline_elapsed_seconds", "graph_assisted_elapsed_seconds",
        "graph_assisted_tool_call_count",
    ):
        item = metrics.get(key)
        if isinstance(item, (int, float)) and not isinstance(item, bool) and item >= 0:
            comparison_values[key] = item
    return {
        "evaluation_id": evaluation_id,
        "provider": str(value.get("provider", "unknown"))[:100],
        "model": str(value.get("model", "unknown"))[:200],
        "source_manifest_sha256": (
            value.get("source_manifest_sha256")
            if isinstance(value.get("source_manifest_sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", value.get("source_manifest_sha256"))
            else "unknown"
        ),
        **compact,
        **comparison_values,
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AE-32C Graph-Utilization Aggregate",
        "",
        f"- Runs: {report['run_count']}",
        f"- Provider/model/backend/snapshot groups: {report['group_count']}",
        "",
        "This report aggregates process telemetry only. It does not estimate diagnostic accuracy, graph benefit, or causal effects.",
        "",
        "## Runs",
        "",
        "| Evaluation | Provider | Model | Backend | Graph queries | Verified graph reads | Graph-citing claims | Baseline tokens | Graph tokens |",
        "|---|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for run in report["runs"]:
        lines.append(
            "| `{}` | {} | {} | {} | {} | {} | {} | {} |".format(
                run["evaluation_id"],
                run["provider"],
                run["model"],
                run.get("active_computation_backend") or "not reported",
                run.get("graph_query_attempt_count", 0),
                run.get("graph_verified_follow_through_path_count", 0),
                run.get("claims_citing_graph_tool_evidence_count", 0),
                run.get("baseline_reported_tokens") if run.get("baseline_reported_tokens") is not None else "not reported",
                run.get("graph_assisted_reported_tokens", run.get("reported_tokens")) if run.get("graph_assisted_reported_tokens", run.get("reported_tokens")) is not None else "not reported",
            )
        )
    lines.extend(["", "## Group summaries", ""])
    for group in report["groups"]:
        lines.extend([
            f"### {group['provider']} / {group['model']} / {group['active_computation_backend']}",
            "",
            f"- Source manifest: `{group['source_manifest_sha256']}`",
            f"- Sample count: {group['sample_count']}",
        ])
        for name, values in group["metrics"].items():
            lines.append(
                f"- {name}: total `{values['total']}`, mean `{values['mean']}` "
                f"(observed runs `{values['observed_run_count']}`)"
            )
        lines.append("")
    lines.extend([
        "## Interpretation limits",
        "",
        "- Groups are separated by provider, model, backend and exact source-manifest hash.",
        "- A graph tool invocation is not proof that its result was used correctly.",
        "- A graph-derived source read is verified only when it follows graph surfacing, is complete for the requested range and matches the graph snapshot hash.",
        "- Claim linkage is ledger-reference linkage, not semantic entailment.",
        "- No diagnostic accuracy, causal benefit, or statistical significance is inferred.",
        "",
    ])
    return "\n".join(lines)


def _publish(report: dict[str, Any], output_dir: Path, checkout_root: Path) -> dict[str, Any]:
    if output_dir.is_symlink():
        raise ValueError("output_directory_must_not_be_symlink")
    out = output_dir.resolve(strict=True)
    checkout = checkout_root.resolve(strict=True)
    if not out.is_dir():
        raise ValueError("output_directory_must_exist")
    try:
        out.relative_to(checkout)
    except ValueError:
        pass
    else:
        raise ValueError("output_directory_must_be_outside_checkout")
    run_id = uuid.uuid4().hex
    staging = out / (".ae32c-graph-utilization-staging-" + run_id)
    final = out / ("ae32c-graph-utilization-" + run_id)
    staging.mkdir(mode=0o700)
    try:
        payloads = {
            "graph_utilization_aggregate.json": (json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8"),
            "graph_utilization_aggregate.md": (_markdown(report).rstrip() + "\n").encode("utf-8"),
        }
        hashes = []
        for name, payload in payloads.items():
            target = staging / name
            fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            hashes.append(f"{hashlib.sha256(payload).hexdigest()}  {name}")
        manifest = ("\n".join(hashes) + "\n").encode("utf-8")
        fd = os.open(str(staging / "SHA256SUMS.txt"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(manifest)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staging, final)
    except Exception:
        import shutil
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "directory": str(final),
        "json": str(final / "graph_utilization_aggregate.json"),
        "markdown": str(final / "graph_utilization_aggregate.md"),
        "manifest": str(final / "SHA256SUMS.txt"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate AE-32C graph-utilization telemetry without provider calls.")
    parser.add_argument("--input", action="append", required=True, help="Published comparison.json; repeat for multiple runs.")
    parser.add_argument("--output-dir", required=True, help="Existing directory outside the repository checkout.")
    args = parser.parse_args(argv)
    if not 1 <= len(args.input) <= MAX_INPUT_FILES:
        parser.error(f"--input must be supplied 1 to {MAX_INPUT_FILES} times")
    try:
        inputs = [Path(item).expanduser() for item in args.input]
        resolved = [item.resolve(strict=True) for item in inputs]
        if len(set(resolved)) != len(resolved):
            raise ValueError("duplicate_input_path")
        runs = [_load_comparison(item) for item in inputs]
        ids = [item["evaluation_id"] for item in runs]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate_evaluation_id")
        aggregate = aggregate_graph_utilization_runs(runs)
        report = {
            **aggregate,
            "runs": runs,
            "inputs": [{"name": item.name, "size_bytes": item.stat().st_size, "sha256": hashlib.sha256(item.read_bytes()).hexdigest()} for item in inputs],
        }
        publication = _publish(report, Path(args.output_dir), Path.cwd())
        print(json.dumps({"status": "published", "run_count": len(runs), "publication": publication}, sort_keys=True, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_code": type(exc).__name__}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
