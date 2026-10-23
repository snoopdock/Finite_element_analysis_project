"""Human-review-oriented comparison helpers for AE-32C evaluation runs.

The helpers summarize observed investigation behavior. They deliberately do
not assign diagnostic-accuracy scores or infer that graph use improved a result.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import uuid

from providers.safe_errors import sanitize_provider_error

SCHEMA_VERSION = "ae32c/evaluation-comparison/v1"
_MAX_REPORT_CHARS = 200_000


def _safe_text(value: Any, limit: int = 8_000) -> str:
    text = str(value).encode("utf-8", "replace").decode("utf-8")
    return sanitize_provider_error(text, limit=limit)


def _source_reference_count(diagnosis: Any) -> int:
    if not isinstance(diagnosis, Mapping):
        return 0
    total = 0
    root = diagnosis.get("root_cause")
    if isinstance(root, Mapping) and isinstance(root.get("source_references"), list):
        total += len(root["source_references"])
    claims = diagnosis.get("claims", [])
    if isinstance(claims, list):
        for claim in claims:
            if isinstance(claim, Mapping) and isinstance(claim.get("source_references"), list):
                total += len(claim["source_references"])
    return total


def summarize_graph_report(report: Mapping[str, Any] | None) -> dict[str, Any]:
    """Extract objective process metrics without scoring diagnosis correctness."""
    if not isinstance(report, Mapping):
        return {
            "status": "not_run",
            "stop_reason": "not_run",
            "model_rounds": 0,
            "tool_call_count": 0,
            "tool_names": [],
            "evidence_count": 0,
            "source_reference_count": 0,
            "diagnosis_assurance": "not_assessed",
            "semantic_claim_support": "requires_independent_adjudication",
            "required_source_coverage_status": "not_assessed",
            "required_source_missing_reads": [],
            "required_source_missing_root_citations": [],
            "final_citation_validation": "not_run",
        }

    budget = report.get("budget") if isinstance(report.get("budget"), Mapping) else {}
    calls = report.get("tool_calls") if isinstance(report.get("tool_calls"), list) else []
    ledger = report.get("evidence_ledger") if isinstance(report.get("evidence_ledger"), list) else []
    actions = report.get("model_actions") if isinstance(report.get("model_actions"), list) else []
    diagnosis = report.get("diagnosis") if isinstance(report.get("diagnosis"), Mapping) else None
    final_validation = "not_accepted"
    for action in actions:
        if isinstance(action, Mapping) and action.get("action") == "final_accepted":
            final_validation = _safe_text(action.get("citation_validation", "accepted"), 100)
    tool_names = sorted({
        _safe_text(call.get("tool", "unknown"), 100)
        for call in calls if isinstance(call, Mapping)
    })
    return {
        "status": _safe_text(report.get("status", "unknown"), 100),
        "stop_reason": _safe_text(report.get("stop_reason", "unknown"), 160),
        "model_rounds": budget.get("model_rounds_used", len(actions)),
        "tool_call_count": len(calls),
        "tool_names": tool_names,
        "evidence_count": len(ledger),
        "source_reference_count": _source_reference_count(diagnosis),
        "diagnosis_assurance": _safe_text(report.get("diagnosis_assurance", "not_assessed"), 120),
        "semantic_claim_support": "requires_independent_adjudication",
        "source_textual_support_status": _safe_text((report.get("source_textual_support") or {}).get("status", "not_assessed") if isinstance(report.get("source_textual_support"), Mapping) else "not_assessed", 80),
        "required_source_coverage_status": _safe_text(
            (report.get("required_source_coverage") or {}).get("status", "not_assessed")
            if isinstance(report.get("required_source_coverage"), Mapping) else "not_assessed", 80
        ),
        "required_source_missing_reads": list(
            (report.get("required_source_coverage") or {}).get("missing_complete_reads", [])
        ) if isinstance(report.get("required_source_coverage"), Mapping) else [],
        "required_source_missing_root_citations": list(
            (report.get("required_source_coverage") or {}).get("missing_root_cause_direct_citations", [])
        ) if isinstance(report.get("required_source_coverage"), Mapping) else [],
        "final_citation_validation": final_validation,
    }


def build_comparison_record(
    *,
    problem_statement: str,
    provider_name: str,
    model_name: str,
    source_manifest_sha256: str | None,
    baseline_status: str,
    baseline_response: str | None,
    baseline_error: str | None,
    baseline_source_path: str,
    baseline_source_sha256: str | None,
    graph_report: Mapping[str, Any] | None,
    baseline_usage: Mapping[str, Any] | None = None,
    baseline_elapsed_seconds: float | None = None,
) -> dict[str, Any]:
    """Build a comparison record that explicitly leaves accuracy to human review."""
    if source_manifest_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", source_manifest_sha256):
        raise ValueError("source_manifest_sha256 must be a lowercase SHA-256 or None")
    if baseline_source_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", baseline_source_sha256):
        raise ValueError("baseline_source_sha256 must be a lowercase SHA-256 or None")
    usage: dict[str, int | float] = {}
    if isinstance(baseline_usage, Mapping):
        for key in ("prompt_tokens", "completion_tokens", "total_tokens", "reported_cost_usd"):
            value = baseline_usage.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            numeric = float(value)
            if math.isfinite(numeric) and numeric >= 0:
                usage[key] = int(numeric) if key != "reported_cost_usd" else round(numeric, 8)
    elapsed = None
    if isinstance(baseline_elapsed_seconds, (int, float)) and not isinstance(baseline_elapsed_seconds, bool):
        numeric_elapsed = float(baseline_elapsed_seconds)
        if math.isfinite(numeric_elapsed) and numeric_elapsed >= 0:
            elapsed = round(numeric_elapsed, 3)
    baseline = {
        "status": _safe_text(baseline_status, 100),
        "response": _safe_text(baseline_response or "", _MAX_REPORT_CHARS),
        "error": _safe_text(baseline_error or "", 500),
        "usage": usage,
        "elapsed_seconds": elapsed,
        "context": {
            "source_path": _safe_text(baseline_source_path, 400),
            "source_sha256": baseline_source_sha256,
            "mode": "single_response_without_evidence_tool_loop",
        },
    }
    graph_summary = summarize_graph_report(graph_report)
    return {
        "schema_version": SCHEMA_VERSION,
        "evaluation_id": "ae32c-eval-" + uuid.uuid4().hex,
        "provider": _safe_text(provider_name, 100),
        "model": _safe_text(model_name or "provider-default-not-reported", 200),
        "problem_statement": _safe_text(problem_statement, 8_000),
        "source_manifest_sha256": source_manifest_sha256,
        "baseline": baseline,
        "graph_assisted": {
            "summary": graph_summary,
            "report": dict(graph_report) if isinstance(graph_report, Mapping) else None,
        },
        "comparison_metrics": {
            "baseline_response_chars": len(baseline["response"]),
            "baseline_reported_tokens": usage.get("total_tokens"),
            "baseline_elapsed_seconds": elapsed,
            "graph_assisted_reported_tokens": (
                (graph_report.get("budget", {}).get("provider_reported_tokens"))
                if isinstance(graph_report, Mapping) and isinstance(graph_report.get("budget"), Mapping)
                else None
            ),
            "graph_assisted_elapsed_seconds": (
                graph_report.get("elapsed_seconds") if isinstance(graph_report, Mapping) else None
            ),
            "graph_assisted_tool_call_count": graph_summary["tool_call_count"],
            "graph_assisted_evidence_count": graph_summary["evidence_count"],
            "graph_assisted_distinct_tool_count": len(graph_summary["tool_names"]),
            "graph_assisted_source_reference_count": graph_summary["source_reference_count"],
            "graph_assisted_required_source_coverage": graph_summary["required_source_coverage_status"],
        },
        "evaluation_policy": {
            "diagnostic_accuracy": "not_automatically_assessed",
            "graph_benefit": "not_claimed_without_independent_comparison",
            "human_review_required": True,
            "resolved_citations_are_not_causal_proof": True,
            "limitations": [
                "A scripted or live model response is not proof of causal correctness.",
                "The two conditions may produce different evidence and token consumption.",
                "Accuracy requires an independently reviewed incident outcome.",
            ],
        },
    }


def _markdown_text(value: Any, limit: int = 4_000) -> str:
    text = _safe_text(value, limit).replace("\r", " ").replace("\n", " ")
    return text.replace("`", "\\`").replace("<", "&lt;").replace(">", "&gt;")


def render_comparison_markdown(record: Mapping[str, Any]) -> str:
    """Render a compact comparison report suitable for manual review."""
    baseline = record.get("baseline") if isinstance(record.get("baseline"), Mapping) else {}
    assisted = record.get("graph_assisted") if isinstance(record.get("graph_assisted"), Mapping) else {}
    summary = assisted.get("summary") if isinstance(assisted.get("summary"), Mapping) else {}
    metrics = record.get("comparison_metrics") if isinstance(record.get("comparison_metrics"), Mapping) else {}
    lines = [
        "# AE-32C Investigation Comparison",
        "",
        f"- Evaluation ID: `{_markdown_text(record.get('evaluation_id', 'unknown'), 100)}`",
        f"- Provider/model: `{_markdown_text(record.get('provider', 'unknown'), 100)}` / `{_markdown_text(record.get('model', 'unknown'), 200)}`",
        f"- Source manifest SHA-256: `{_markdown_text(record.get('source_manifest_sha256') or 'not available', 100)}`",
        "",
        "## Problem statement",
        "",
        _markdown_text(record.get("problem_statement", ""), 8_000),
        "",
        "## Baseline: error plus basic source context",
        "",
        f"- Status: `{_markdown_text(baseline.get('status', 'unknown'), 100)}`",
        f"- Context: `{_markdown_text((baseline.get('context') or {}).get('source_path', 'unknown'), 400)}`",
        f"- Response characters: {metrics.get('baseline_response_chars', 0)}",
        f"- Reported tokens: {metrics.get('baseline_reported_tokens', 'not reported')}",
        f"- Elapsed seconds: {metrics.get('baseline_elapsed_seconds', 'not measured')}",
        "",
        _markdown_text(baseline.get("response", "No baseline response was captured."), 8_000),
        "",
        "## Graph-assisted investigation",
        "",
        f"- Status: `{_markdown_text(summary.get('status', 'unknown'), 100)}`",
        f"- Stop reason: `{_markdown_text(summary.get('stop_reason', 'unknown'), 160)}`",
        f"- Model rounds: {summary.get('model_rounds', 0)}",
        f"- Tool calls: {metrics.get('graph_assisted_tool_call_count', 0)}",
        f"- Reported tokens: {metrics.get('graph_assisted_reported_tokens', 'not reported')}",
        f"- Elapsed seconds: {metrics.get('graph_assisted_elapsed_seconds', 'not measured')}",
        f"- Distinct tools: {', '.join(_markdown_text(x, 100) for x in summary.get('tool_names', []))}",
        f"- Evidence records: {metrics.get('graph_assisted_evidence_count', 0)}",
        f"- Source references: {metrics.get('graph_assisted_source_reference_count', 0)}",
        f"- Citation validation: `{_markdown_text(summary.get('final_citation_validation', 'not assessed'), 100)}`",
        f"- Declared source-inspection coverage: `{_markdown_text(summary.get('required_source_coverage_status', 'not assessed'), 80)}`",
        f"- Missing complete direct reads: {', '.join(_markdown_text(p, 400) for p in summary.get('required_source_missing_reads', [])) or 'none'}",
        f"- Missing direct root-cause citations: {', '.join(_markdown_text(p, 400) for p in summary.get('required_source_missing_root_citations', [])) or 'none'}",
        "",
    ]
    report = assisted.get("report")
    diagnosis = report.get("diagnosis") if isinstance(report, Mapping) else None
    if isinstance(diagnosis, Mapping):
        root = diagnosis.get("root_cause") if isinstance(diagnosis.get("root_cause"), Mapping) else {}
        lines.extend(["### Graph-assisted assessment", "", _markdown_text(diagnosis.get("summary", ""), 4_000), "", _markdown_text(root.get("statement", ""), 4_000), ""])
    lines.extend([
        "## Review requirements",
        "",
        "- [ ] Independently verify each material source and graph citation.",
        "- [ ] Compare both diagnoses against the independently reviewed incident outcome.",
        "- [ ] Record unsupported claims, missed evidence, and any misleading graph relationships.",
        "- [ ] Do not infer accuracy or graph benefit from tool usage or response length alone.",
        "",
        "**Automated diagnostic accuracy:** not assessed. Human review is required.",
        "",
    ])
    return "\n".join(lines)


def write_comparison_artifacts(
    record: Mapping[str, Any],
    *,
    output_dir: str | Path,
    checkout_root: str | Path,
) -> dict[str, Any]:
    """Atomically publish a new comparison directory outside the checkout."""
    supplied = Path(output_dir).expanduser()
    if supplied.is_symlink():
        raise ValueError("output_directory_must_not_be_symlink")
    out = supplied.resolve(strict=True)
    checkout = Path(checkout_root).expanduser().resolve(strict=True)
    if not out.is_dir():
        raise ValueError("output_directory_must_exist")
    try:
        out.relative_to(checkout)
    except ValueError:
        pass
    else:
        raise ValueError("output_directory_must_be_outside_checkout")

    json_bytes = (json.dumps(record, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    markdown_bytes = (render_comparison_markdown(record).rstrip() + "\n").encode("utf-8")
    run_id = uuid.uuid4().hex
    staging = out / (".ae32c-evaluation-staging-" + run_id)
    final = out / ("ae32c-evaluation-" + run_id)
    staging.mkdir(mode=0o700)
    try:
        files = {"comparison.json": json_bytes, "comparison.md": markdown_bytes}
        hashes = []
        for name, payload in files.items():
            path = staging / name
            descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            hashes.append(f"{hashlib.sha256(payload).hexdigest()}  {name}")
        manifest = ("\n".join(hashes) + "\n").encode("utf-8")
        descriptor = os.open(str(staging / "SHA256SUMS.txt"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(manifest)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staging, final)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "publication": "atomic_directory_rename",
        "directory": str(final),
        "artifacts": [
            {"path": str(final / name), "sha256": hashlib.sha256(payload).hexdigest(), "size_bytes": len(payload)}
            for name, payload in files.items()
        ],
        "manifest_path": str(final / "SHA256SUMS.txt"),
    }
