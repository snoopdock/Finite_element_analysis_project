#!/usr/bin/env python3
"""Create a credential-free summary for one full FEA provider benchmark run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict


ARTIFACT_PATHS = (
    "artifacts/benchmark/pipeline.log",
    "artifacts/benchmark/publication-validation.log",
    "artifacts/benchmark/pipeline-start-epoch.json",
    "artifacts/benchmark/pipeline-end-epoch.json",
    "output/provider_runtime_diagnostics.json",
    "output/provider_runtime_diagnostics.error.txt",
    "output/guideline.pdf",
    "output/guideline.tex",
    "output/guideline.log",
    "output/publication_manifest.json",
    "output/document.semantic-candidate.json",
    "output/evidence.json",
    "output/research.json",
    "output/sections.json",
    "output/validation_report.md",
    "output/error.txt",
    "state/current_state.json",
    "state/reading_state.json",
)


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def _count_report_errors(state: Dict[str, Any], report_text: str) -> Any:
    """Count operational errors from state or the generated report, without double counting."""
    state_errors = state.get("errors")
    state_count = len(state_errors) if isinstance(state_errors, list) else None
    report_count = None
    marker = "## Errors"
    if marker in report_text:
        section = report_text.split(marker, 1)[1]
        section = section.split("\\n## ", 1)[0]
        report_count = sum(1 for line in section.splitlines() if line.lstrip().startswith("- "))
    elif "## Status: SUCCESS" in report_text:
        report_count = 0
    if state_count is None:
        return report_count
    if report_count is None:
        return state_count
    return max(state_count, report_count)


def _runtime_diagnostics_summary(repo_root: Path, state: Dict[str, Any]) -> Dict[str, Any]:
    disk_record = _read_json(repo_root / "output" / "provider_runtime_diagnostics.json", {})
    if not isinstance(disk_record, dict):
        disk_record = {}
    runtime = state.get("provider_runtime_diagnostics", {})
    if not isinstance(runtime, dict):
        runtime = {}
    source = disk_record or runtime
    events = source.get("phase_events", [])
    if not isinstance(events, list):
        events = []
    return {
        "status": source.get("status", "not_recorded"),
        "active_phase": source.get("active_phase"),
        "source_commit": source.get("source_commit", "unknown"),
        "workflow_commit": source.get("workflow_commit", "unknown"),
        "phases": [
            {
                "phase": event.get("phase", "unknown"),
                "status": event.get("status", "unknown"),
                "delta": event.get("delta", {}),
                "error_type": event.get("error_type"),
                "error": event.get("error"),
            }
            for event in events[-40:]
            if isinstance(event, dict)
        ],
        "failure": source.get("failure"),
    }


def _file_record(path: Path, root: Path) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "path": str(path.relative_to(root)),
        "exists": path.is_file(),
    }
    if not path.is_file():
        return record
    data = path.read_bytes()
    record.update({
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    })
    return record


def build_summary(repo_root: Path, metadata: Dict[str, Any]) -> Dict[str, Any]:
    root = repo_root.resolve()
    state = _read_json(root / "state" / "current_state.json", {})
    if not isinstance(state, dict):
        state = {}
    usage = state.get("model_usage", {})
    if not isinstance(usage, dict):
        usage = {}

    report_path = root / "output" / "validation_report.md"
    try:
        report_text = report_path.read_text(encoding="utf-8")
    except OSError:
        report_text = ""

    pipeline_outcome = str(metadata.get("pipeline_outcome", "unknown"))
    publication_outcome = str(metadata.get("publication_outcome", "not_run"))
    source_commit = str(
        metadata.get("source_commit")
        or metadata.get("commit")
        or os.environ.get("FEA_SOURCE_COMMIT")
        or "unknown"
    )
    workflow_commit = str(
        metadata.get("workflow_commit")
        or os.environ.get("FEA_WORKFLOW_COMMIT")
        or os.environ.get("GITHUB_SHA")
        or "unknown"
    )
    started_epoch = _read_json(root / "artifacts" / "benchmark" / "pipeline-start-epoch.json", None)
    ended_epoch = _read_json(root / "artifacts" / "benchmark" / "pipeline-end-epoch.json", None)
    # Epoch files are intentionally JSON numbers so the report remains robust
    # to localized shell date output.
    duration_seconds = None
    if isinstance(started_epoch, (int, float)) and isinstance(ended_epoch, (int, float)):
        duration_seconds = max(0.0, float(ended_epoch) - float(started_epoch))
    pipeline_status = "success" if pipeline_outcome == "success" else "failed_or_incomplete"
    publication_status = (
        "passed" if publication_outcome == "success"
        else "failed" if publication_outcome == "failure"
        else "not_run"
    )

    return {
        "schema_version": 1,
        "benchmark": {
            "provider": str(metadata.get("provider", os.environ.get("FEA_LLM_PROVIDER", "unknown"))),
            "model": str(metadata.get("model", os.environ.get("FEA_LLM_MODEL", "unknown"))),
            "target_branch": str(metadata.get("target_branch", os.environ.get("FEA_BENCHMARK_TARGET_BRANCH", "unknown"))),
            # `commit` remains as a compatibility alias for the actual source checkout.
            "commit": source_commit,
            "source_commit": source_commit,
            "workflow_commit": workflow_commit,
            "max_tokens_per_call": int(metadata.get("max_tokens_per_call", os.environ.get("FEA_MAX_TOKENS_PER_CALL", 0)) or 0),
            "max_llm_calls": int(metadata.get("max_llm_calls", os.environ.get("FEA_MAX_LLM_CALLS", 0)) or 0),
            "pipeline_outcome": pipeline_outcome,
            "pipeline_status": pipeline_status,
            "pipeline_duration_seconds": duration_seconds,
            "publication_outcome": publication_outcome,
            "publication_status": publication_status,
            "reported_pipeline_status": str(state.get("last_run_status", "unknown")),
            "cycle": state.get("cycle"),
            "iteration": state.get("iteration"),
            "errors_recorded": _count_report_errors(state, report_text),
            "validation_report_contains_success": "## Status: SUCCESS" in report_text,
            "validation_report_contains_errors": "## Errors" in report_text,
        },
        "model_usage": usage,
        "parser_stats": state.get("parser_stats", {}) if isinstance(state.get("parser_stats", {}), dict) else {},
        "provider_runtime_diagnostics": _runtime_diagnostics_summary(root, state),
        "artifacts": [_file_record(root / relative, root) for relative in ARTIFACT_PATHS],
        "secret_values_included": False,
    }


def render_markdown(summary: Dict[str, Any]) -> str:
    benchmark = summary["benchmark"]
    usage = summary.get("model_usage", {})
    lines = [
        "# FEA LLM Provider Benchmark Result",
        "",
        f"- Provider: `{benchmark['provider']}`",
        f"- Model: `{benchmark['model']}`",
        f"- Target branch: `{benchmark['target_branch']}`",
        f"- Source checkout commit: `{benchmark.get('source_commit', benchmark['commit'])}`",
        f"- Workflow commit: `{benchmark.get('workflow_commit', 'unknown')}`",
        f"- Token cap per call: `{benchmark['max_tokens_per_call']}`",
        f"- Logical-call cap: `{benchmark['max_llm_calls']}`",
        f"- Pipeline outcome: `{benchmark['pipeline_outcome']}`",
        f"- Pipeline duration (seconds): `{benchmark.get('pipeline_duration_seconds', 'not recorded')}`",
        f"- Publication validation: `{benchmark['publication_status']}`",
        f"- Application-reported run status: `{benchmark['reported_pipeline_status']}`",
        "",
        "## Provider usage",
        "",
        f"- Logical calls: `{usage.get('logical_calls', usage.get('total_calls', 'not reported'))}`",
        f"- Successful calls: `{usage.get('successful_calls', 'not reported')}`",
        f"- Failed calls: `{usage.get('failed_calls', 'not reported')}`",
        f"- HTTP attempts: `{usage.get('http_attempts', 'not reported')}`",
    ]
    token_usage = usage.get("usage")
    if isinstance(token_usage, dict):
        lines.extend([
            f"- Prompt tokens reported: `{token_usage.get('prompt_tokens', 'not reported')}`",
            f"- Completion tokens reported: `{token_usage.get('completion_tokens', 'not reported')}`",
            f"- Total tokens reported: `{token_usage.get('total_tokens', 'not reported')}`",
        ])
        if int(token_usage.get("responses_with_cost", 0) or 0) > 0:
            lines.append(f"- Provider-reported cost (USD): `{token_usage.get('reported_cost_usd')}`")
    lines.extend([
        "",
        "## Runtime phase trace",
        "",
        f"- Diagnostic status: `{summary.get('provider_runtime_diagnostics', {}).get('status', 'not_recorded')}`",
        f"- Active phase at failure: `{summary.get('provider_runtime_diagnostics', {}).get('active_phase') or 'none'}`",
    ])
    phases = summary.get("provider_runtime_diagnostics", {}).get("phases", [])
    if phases:
        lines.extend(["", "| Phase | Status | Logical-call delta | HTTP-attempt delta | Error |", "|---|---|---:|---:|---|"])
        for event in phases:
            delta = event.get("delta", {}) if isinstance(event.get("delta"), dict) else {}
            error = event.get("error") or event.get("error_type") or ""
            lines.append(
                f"| `{event.get('phase', 'unknown')}` | `{event.get('status', 'unknown')}` | "
                f"{delta.get('logical_calls', '')} | {delta.get('http_attempts', '')} | "
                f"{str(error).replace('|', '/')} |"
            )
    lines.extend(["", "## Artifact manifest", "", "| Path | Present | Size (bytes) | SHA-256 |", "|---|---:|---:|---|"])
    for item in summary["artifacts"]:
        lines.append(
            f"| `{item['path']}` | {'yes' if item['exists'] else 'no'} | "
            f"{item.get('size_bytes', '')} | `{item.get('sha256', '')}` |"
        )
    lines.extend([
        "",
        "This report contains operational metrics and artifact digests, not provider credentials. "
        "A successful API response or publication validation does not establish scientific correctness.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output-dir", default="artifacts/benchmark")
    parser.add_argument("--provider", default=os.environ.get("FEA_LLM_PROVIDER", "unknown"))
    parser.add_argument("--model", default=os.environ.get("FEA_LLM_MODEL", "unknown"))
    parser.add_argument("--target-branch", default=os.environ.get("FEA_BENCHMARK_TARGET_BRANCH", "unknown"))
    parser.add_argument("--max-tokens-per-call", type=int, default=int(os.environ.get("FEA_MAX_TOKENS_PER_CALL", "0") or 0))
    parser.add_argument("--max-llm-calls", type=int, default=int(os.environ.get("FEA_MAX_LLM_CALLS", "0") or 0))
    parser.add_argument("--pipeline-outcome", default=os.environ.get("FEA_PIPELINE_OUTCOME", "unknown"))
    parser.add_argument("--publication-outcome", default=os.environ.get("FEA_PUBLICATION_OUTCOME", "not_run"))
    parser.add_argument("--commit", default=None, help="Legacy alias for source commit")
    parser.add_argument("--source-commit", default=os.environ.get("FEA_SOURCE_COMMIT", ""))
    parser.add_argument("--workflow-commit", default=os.environ.get("FEA_WORKFLOW_COMMIT", os.environ.get("GITHUB_SHA", "")))
    args = parser.parse_args()

    metadata = {
        "provider": args.provider,
        "model": args.model,
        "target_branch": args.target_branch,
        "source_commit": args.source_commit,
        "workflow_commit": args.workflow_commit,
        "commit": args.commit,
        "max_tokens_per_call": args.max_tokens_per_call,
        "max_llm_calls": args.max_llm_calls,
        "pipeline_outcome": args.pipeline_outcome,
        "publication_outcome": args.publication_outcome,
        "commit": args.commit,
    }
    summary = build_summary(Path(args.repo_root), metadata)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "provider-benchmark-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "provider-benchmark-summary.md").write_text(
        render_markdown(summary), encoding="utf-8"
    )
    print(json.dumps(summary["benchmark"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
