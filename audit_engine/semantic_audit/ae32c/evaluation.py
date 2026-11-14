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


def _safe_request_diagnostics(value: Any) -> dict[str, Any]:
    """Copy only bounded, non-sensitive request timing/configuration telemetry."""
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key in (
        "elapsed_seconds",
        "time_to_first_event_seconds",
        "time_to_first_output_seconds",
        "connect_timeout_seconds",
        "read_timeout_seconds",
    ):
        item = value.get(key)
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            number = float(item)
            if math.isfinite(number) and 0 <= number <= 3600:
                result[key] = round(number, 3)
    for key in (
        "attempt_count",
        "stream_event_count",
        "output_chars",
        "partial_output_chars",
        "max_completion_tokens",
    ):
        item = value.get(key)
        if isinstance(item, int) and not isinstance(item, bool) and 0 <= item <= 2_000_000:
            result[key] = item
    if isinstance(value.get("streaming"), bool):
        result["streaming"] = value["streaming"]
    if isinstance(value.get("reasoning_effort"), str) and value["reasoning_effort"] in {"low", "medium", "high"}:
        result["reasoning_effort"] = value["reasoning_effort"]
    if isinstance(value.get("finish_reason"), str) and value["finish_reason"] in {"", "stop", "tool_calls", "length", "content_filter", "function_call"}:
        result["finish_reason"] = value["finish_reason"]
    if isinstance(value.get("error_type"), str) and value["error_type"] in {"", "ReadTimeout", "ConnectTimeout", "ConnectionError", "Timeout", "ChunkedEncodingError", "StreamProtocolError"}:
        result["error_type"] = value["error_type"]
    if isinstance(value.get("error_category"), str) and value["error_category"] in {"none", "read_timeout", "connect_timeout", "transport_error", "stream_interrupted", "provider_request_rejected", "invalid_provider_json", "invalid_stream"}:
        result["error_category"] = value["error_category"]
    return result


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
            "investigation_context_coverage_status": "not_assessed",
            "static_execution_context_status": "not_assessed",
            "related_test_context_status": "not_assessed",
            "case_metadata_context_status": "not_assessed",
            "runtime_reproduction_status": "not_assessed",
        }

    budget = report.get("budget") if isinstance(report.get("budget"), Mapping) else {}
    interaction = report.get("interaction_diagnostics") if isinstance(report.get("interaction_diagnostics"), Mapping) else {}
    mode_record = interaction.get("response_mode_negotiation") if isinstance(interaction.get("response_mode_negotiation"), Mapping) else {}
    initial_mode = mode_record.get("initial_mode")
    last_mode = mode_record.get("last_mode")
    session_override = mode_record.get("session_override")
    if not isinstance(initial_mode, str) or initial_mode not in {"json_schema", "native_tool_call", "json_object", "plain_text", "not_observed"}:
        initial_mode = "not_reported"
    if not isinstance(last_mode, str) or last_mode not in {"json_schema", "native_tool_call", "json_object", "plain_text", "unknown"}:
        last_mode = "not_reported"
    if not isinstance(session_override, str) or session_override not in {"plain_text", "none"}:
        session_override = "not_reported"
    mode_summary = {
        "initial_mode": initial_mode,
        "last_mode": last_mode,
        "session_override": session_override,
        "plain_text_downgrade_used": mode_record.get("plain_text_downgrade_used") is True,
        "last_endpoint_mode": (
            mode_record.get("last_endpoint_mode")
            if isinstance(mode_record.get("last_endpoint_mode"), str)
            and re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", mode_record.get("last_endpoint_mode"))
            else "not_reported"
        ),
    }
    calls = report.get("tool_calls") if isinstance(report.get("tool_calls"), list) else []
    ledger = report.get("evidence_ledger") if isinstance(report.get("evidence_ledger"), list) else []
    actions = report.get("model_actions") if isinstance(report.get("model_actions"), list) else []
    diagnosis = report.get("diagnosis") if isinstance(report.get("diagnosis"), Mapping) else None
    context = report.get("investigation_context_coverage") if isinstance(report.get("investigation_context_coverage"), Mapping) else {}
    static_context = context.get("static_execution_context") if isinstance(context.get("static_execution_context"), Mapping) else {}
    test_context = context.get("related_test_context") if isinstance(context.get("related_test_context"), Mapping) else {}
    metadata_context = context.get("case_metadata_context") if isinstance(context.get("case_metadata_context"), Mapping) else {}
    execution_assessment = report.get("execution_assessment") if isinstance(report.get("execution_assessment"), Mapping) else {}
    provider_record = report.get("provider") if isinstance(report.get("provider"), Mapping) else {}
    request_diagnostics = _safe_request_diagnostics(provider_record.get("request_diagnostics"))
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
        "investigation_context_coverage_status": _safe_text(context.get("status", "not_assessed"), 100),
        "investigation_context_candidate_count": int(context.get("candidate_context_path_count", 0)) if isinstance(context.get("candidate_context_path_count", 0), int) and not isinstance(context.get("candidate_context_path_count", 0), bool) else 0,
        "investigation_context_read_count": int(context.get("candidate_context_paths_read_count", 0)) if isinstance(context.get("candidate_context_paths_read_count", 0), int) and not isinstance(context.get("candidate_context_paths_read_count", 0), bool) else 0,
        "investigation_context_unread_count": int(context.get("candidate_context_paths_not_read_count", 0)) if isinstance(context.get("candidate_context_paths_not_read_count", 0), int) and not isinstance(context.get("candidate_context_paths_not_read_count", 0), bool) else 0,
        "investigation_context_unread_paths": [
            _safe_text(path, 400) for path in context.get("candidate_context_paths_not_read", [])[:60]
            if isinstance(path, str)
        ] if isinstance(context.get("candidate_context_paths_not_read", []), list) else [],
        "test_classification_counts": dict(context.get("test_classification_counts", {})) if isinstance(context.get("test_classification_counts", {}), Mapping) else {},
        "static_execution_context_status": _safe_text(static_context.get("status", "not_assessed"), 100),
        "related_test_context_status": _safe_text(test_context.get("status", "not_assessed"), 100),
        "case_metadata_context_status": _safe_text(metadata_context.get("status", "not_assessed"), 100),
        "runtime_reproduction_status": _safe_text(execution_assessment.get("runtime_reproduction_status", "not_assessed"), 100),
        "response_mode_negotiation": mode_summary,
        "provider_request_diagnostics": request_diagnostics,
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
    baseline_provider_diagnostics: Mapping[str, Any] | None = None,
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
    # Redaction-by-construction: only fixed enums from the provider adapter,
    # never raw HTTP responses or upstream error messages.
    known_errors = {"malformed_completion_envelope", "transport_error", "http_error",
        "provider_api_error_payload", "invalid_json_response", "completion_truncated",
        "completion_filtered", "response_too_large", "response_text_too_large",
        "empty_completion_content", "response_stream_error", "transient_http_status_exhausted",
        "logical_call_budget_exhausted", "retry_budget_exhausted"}
    known_envelopes = {"standard_choices", "upstream_error_object", "alternate_wrapper",
        "unrecognized_object", "non_object"}
    known_shapes = {"nonempty_list", "empty_list", "absent", "wrong_type"}
    diagnostics = baseline_provider_diagnostics if isinstance(baseline_provider_diagnostics, Mapping) else {}
    baseline_call_interface = diagnostics.get("baseline_call_interface")
    if not isinstance(baseline_call_interface, str) or baseline_call_interface not in {"chat_text", "chat"}:
        baseline_call_interface = "not_reported"
    baseline_request_diagnostics = _safe_request_diagnostics(diagnostics.get("request_diagnostics"))
    baseline_endpoint_mode = diagnostics.get("last_endpoint_mode")
    if (not isinstance(baseline_endpoint_mode, str)
            or re.fullmatch(r"[a-zA-Z0-9_.-]{1,120}", baseline_endpoint_mode) is None):
        baseline_endpoint_mode = "not_reported"
    baseline_finish_reason = diagnostics.get("last_finish_reason")
    if baseline_finish_reason not in {"stop", "tool_calls", "length", "content_filter", "function_call"}:
        baseline_finish_reason = None
    error_code = diagnostics.get("last_error_code")
    error_code = error_code if isinstance(error_code, str) and error_code in known_errors else "unclassified_or_none"
    envelope = diagnostics.get("last_envelope_diagnostic")
    envelope = envelope if isinstance(envelope, Mapping) else {}
    shape = envelope.get("choices_shape")
    kind = envelope.get("envelope_kind")
    baseline = {
        "error_code": error_code,
        "envelope_diagnostic": {
            "envelope_kind": kind if isinstance(kind, str) and kind in known_envelopes else "not_observed",
            "choices_shape": shape if isinstance(shape, str) and shape in known_shapes else "not_observed",
            "has_error_object": envelope.get("has_error_object") is True,
        },
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
        "transport": {
            "call_interface": baseline_call_interface,
            "endpoint_mode": baseline_endpoint_mode,
            "request_diagnostics": baseline_request_diagnostics,
            **({"finish_reason": baseline_finish_reason} if baseline_finish_reason is not None else {}),
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
        f"- Provider error category: `{_markdown_text(baseline.get('error_code', 'not_reported'), 100)}`",
        f"- Envelope shape category: `{_markdown_text((baseline.get('envelope_diagnostic') or {}).get('envelope_kind', 'not_observed'), 100)}`",
        f"- Context: `{_markdown_text((baseline.get('context') or {}).get('source_path', 'unknown'), 400)}`",
        f"- Request interface: `{_markdown_text((baseline.get('transport') or {}).get('call_interface', 'not_reported'), 80)}`",
        f"- Endpoint mode: `{_markdown_text((baseline.get('transport') or {}).get('endpoint_mode', 'not_reported'), 120)}`",
        f"- Finish reason: `{_markdown_text((baseline.get('transport') or {}).get('finish_reason', 'not_reported'), 40)}`",
        f"- Response streaming: `{bool(((baseline.get('transport') or {}).get('request_diagnostics') or {}).get('streaming'))}`",
        f"- Time to first event/output: `{((baseline.get('transport') or {}).get('request_diagnostics') or {}).get('time_to_first_event_seconds', 'n/a')}s / {((baseline.get('transport') or {}).get('request_diagnostics') or {}).get('time_to_first_output_seconds', 'n/a')}s`",
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
        f"- Initial response mode: `{_markdown_text((summary.get('response_mode_negotiation') or {}).get('initial_mode', 'not_reported'), 80)}`",
        f"- Last response mode: `{_markdown_text((summary.get('response_mode_negotiation') or {}).get('last_mode', 'not_reported'), 80)}`",
        f"- Plain-text downgrade used: `{bool((summary.get('response_mode_negotiation') or {}).get('plain_text_downgrade_used'))}`",
        f"- Last endpoint mode: `{_markdown_text((summary.get('response_mode_negotiation') or {}).get('last_endpoint_mode', 'not_reported'), 120)}`",
        f"- Graph streaming: `{bool((summary.get('provider_request_diagnostics') or {}).get('streaming'))}`",
        f"- Graph time to first event/output: `{(summary.get('provider_request_diagnostics') or {}).get('time_to_first_event_seconds', 'n/a')}s / {(summary.get('provider_request_diagnostics') or {}).get('time_to_first_output_seconds', 'n/a')}s`",
        f"- Graph finish reason: `{_markdown_text((summary.get('provider_request_diagnostics') or {}).get('finish_reason', 'not_reported'), 40)}`",
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
