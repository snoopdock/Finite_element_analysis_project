"""Operational diagnostics for LLM provider calls and pipeline phase boundaries.

This module records metadata only. It does not inspect, rewrite, or evaluate scientific prose.
Provider responses are untrusted; secrets are redacted before diagnostics are persisted.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional


_SECRET_ENV_NAMES = (
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_ACCOUNT_ID",
    "NARAROUTER_API_KEY",
    "OPENROUTER_TOKEN",
)
_COUNTER_KEYS = (
    "logical_calls",
    "total_calls",
    "successful_calls",
    "failed_calls",
    "http_attempts",
    "response_chars_total",
)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact_runtime_text(value: Any, limit: int = 1500) -> str:
    """Bound and redact provider secrets from operational messages."""
    text = str(value)
    for name in _SECRET_ENV_NAMES:
        secret = os.environ.get(name, "")
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(
        r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;\"']+",
        r"\1[REDACTED]",
        text,
    )
    text = re.sub(
        r"(?i)(api[_-]?key|access[_-]?token|secret)\s*([=:]\s*)[^\s,;\"']+",
        r"\1\2[REDACTED]",
        text,
    )
    return text[:max(0, int(limit))]


def _sanitize(value: Any, depth: int = 0) -> Any:
    """Convert provider telemetry to bounded, JSON-safe, redacted values."""
    if depth > 6:
        return "[DEPTH_LIMIT]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return redact_runtime_text(value, limit=2000)
    if isinstance(value, dict):
        result = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 100:
                result["_truncated_items"] = len(value) - 100
                break
            result[redact_runtime_text(key, limit=100)] = _sanitize(item, depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        items = [_sanitize(item, depth + 1) for item in value[:50]]
        if len(value) > 50:
            items.append({"_truncated_items": len(value) - 50})
        return items
    return redact_runtime_text(value, limit=500)


def safe_provider_stats(provider: Any) -> Dict[str, Any]:
    """Return sanitized provider telemetry without exposing credentials."""
    if provider is None:
        return {}
    getter = getattr(provider, "get_stats", None)
    if callable(getter):
        try:
            stats = getter()
        except Exception as exc:
            return {"stats_error": redact_runtime_text(exc)}
        if isinstance(stats, dict):
            return _sanitize(stats)
        return {"stats_error": "provider.get_stats() returned a non-mapping"}
    return {
        "provider": redact_runtime_text(getattr(provider, "provider_name", "unknown"), 100),
        "model": redact_runtime_text(getattr(provider, "model", "unknown"), 200),
    }


def get_provider_call_count(provider: Any) -> int:
    """Read a provider's logical-call count through supported interface aliases.

    `logical_calls` is preferred. `total_calls` remains supported for older
    providers. If neither exists, use the same fields in get_stats(); fail
    clearly rather than silently treating an unknown count as zero.
    """
    for field in ("logical_calls", "total_calls"):
        try:
            value = getattr(provider, field, None)
        except Exception:
            value = None
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    stats = safe_provider_stats(provider)
    for field in ("logical_calls", "total_calls"):
        value = stats.get(field)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    raise TypeError(
        "LLM provider must expose a non-negative logical_calls or total_calls counter"
    )


def provider_snapshot(provider: Any) -> Dict[str, Any]:
    """Return a compact operational snapshot suitable for a phase event."""
    stats = safe_provider_stats(provider)
    selected = (
        "provider", "model", "endpoint", "total_calls", "logical_calls",
        "successful_calls", "failed_calls", "http_attempts",
        "http_status_counts", "last_http_status", "last_returned_model",
        "finish_reason_counts", "response_chars_total", "response_chars_max",
        "max_logical_calls", "max_tokens_per_call", "timeout_seconds",
        "max_retries", "usage", "per_model", "last_errors",
    )
    snapshot = {key: stats[key] for key in selected if key in stats}
    snapshot.setdefault(
        "provider",
        redact_runtime_text(getattr(provider, "provider_name", "unknown"), 100)
        if provider is not None else "unknown",
    )
    snapshot.setdefault(
        "model",
        redact_runtime_text(getattr(provider, "model", "unknown"), 200)
        if provider is not None else "unknown",
    )
    return snapshot


def _counter_delta(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    delta: Dict[str, Any] = {}
    for key in _COUNTER_KEYS:
        old = before.get(key, 0)
        new = after.get(key, 0)
        if isinstance(old, int) and isinstance(new, int):
            delta[key] = new - old
    old_usage = before.get("usage", {})
    new_usage = after.get("usage", {})
    if isinstance(old_usage, dict) and isinstance(new_usage, dict):
        usage_delta = {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens", "responses_with_usage"):
            old = old_usage.get(key, 0)
            new = new_usage.get(key, 0)
            if isinstance(old, (int, float)) and isinstance(new, (int, float)):
                usage_delta[key] = new - old
        if usage_delta:
            delta["usage"] = usage_delta
    return delta


def record_provider_phase(
    state: Dict[str, Any],
    provider: Any,
    phase: str,
    status: str,
    before: Optional[Dict[str, Any]] = None,
    error: Optional[BaseException] = None,
) -> Dict[str, Any]:
    """Append a bounded phase event showing provider usage before/after a phase."""
    runtime = state.get("provider_runtime_diagnostics")
    if not isinstance(runtime, dict):
        runtime = {"schema_version": 1, "phase_events": []}
        state["provider_runtime_diagnostics"] = runtime
    events = runtime.get("phase_events")
    if not isinstance(events, list):
        events = []
    after = provider_snapshot(provider)
    before_snapshot = before if isinstance(before, dict) else after
    event: Dict[str, Any] = {
        "phase": redact_runtime_text(phase, 100),
        "status": redact_runtime_text(status, 50),
        "timestamp_utc": utc_timestamp(),
        "before": _sanitize(before_snapshot),
        "after": after,
        "delta": _counter_delta(before_snapshot, after),
    }
    if error is not None:
        event["error_type"] = type(error).__name__
        event["error"] = redact_runtime_text(error)
    events.append(event)
    runtime["phase_events"] = events[-40:]
    runtime["last_snapshot"] = after
    runtime["active_phase"] = None if status in ("completed", "skipped", "failed") else phase
    return event


def finalize_provider_diagnostics(
    state: Dict[str, Any],
    provider: Any,
    status: str,
    active_phase: Optional[str] = None,
    error: Optional[BaseException] = None,
) -> Dict[str, Any]:
    """Finalize this run's operational trace without altering pipeline decisions."""
    runtime = state.get("provider_runtime_diagnostics")
    if not isinstance(runtime, dict):
        runtime = {"schema_version": 1, "phase_events": []}
        state["provider_runtime_diagnostics"] = runtime
    runtime["schema_version"] = 1
    runtime["status"] = redact_runtime_text(status, 50)
    runtime["active_phase"] = redact_runtime_text(active_phase, 100) if active_phase else None
    runtime["source_commit"] = os.environ.get("FEA_SOURCE_COMMIT", "unknown")
    runtime["workflow_commit"] = os.environ.get("FEA_WORKFLOW_COMMIT", os.environ.get("GITHUB_SHA", "unknown"))
    runtime["final_snapshot"] = provider_snapshot(provider)
    if error is not None:
        runtime["failure"] = {
            "phase": runtime["active_phase"] or "unknown",
            "exception_type": type(error).__name__,
            "message": redact_runtime_text(error),
            "timestamp_utc": utc_timestamp(),
        }
    return runtime
