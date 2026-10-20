"""Manual, bounded provider compatibility preflight for AE-32C.

This command makes no repository-tool calls and never executes the incident fixture.
It first checks that the selected provider returns non-empty content. For Cloudflare
only, it then probes the current model's ability to return the same strict JSON action
shape expected by the investigator. The JSON probe is prompt-only: it does not claim
that an API-level constrained-output feature is supported.

Live calls require an explicit confirmation flag. Artifacts intentionally omit raw
model response bodies and credentials.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Callable, Mapping

from providers.factory import SUPPORTED_PROVIDERS, build_provider
from providers.safe_errors import sanitize_provider_error

DEFAULT_CLOUDFLARE_MODEL = "@cf/meta/llama-3.1-8b-instruct-fast"
BASELINE_SENTINEL = "AE32C_PREFLIGHT_OK"


def _effective_model(provider: Any, requested: str) -> str:
    if isinstance(requested, str) and requested.strip():
        return requested.strip()[:200]
    model = getattr(provider, "model", None)
    if isinstance(model, str) and model.strip():
        return model.strip()[:200]
    models = getattr(provider, "models", None)
    if isinstance(models, (list, tuple)) and models and isinstance(models[0], str):
        return models[0][:200]
    return "provider-default-not-reported"


def _safe_error(error: Any) -> str:
    if not error:
        return ""
    return sanitize_provider_error(str(error), limit=300)


def _provider_runtime_settings(provider: Any) -> dict[str, Any]:
    try:
        stats = provider.get_stats()
    except Exception:
        return {}
    if not isinstance(stats, dict):
        return {}
    allowed = (
        "timeout_seconds", "max_retries", "http_attempts", "http_status_counts",
        "successful_calls", "failed_calls", "logical_calls", "total_calls",
        "last_http_status", "last_returned_model", "finish_reason_counts",
    )
    return {key: stats[key] for key in allowed if key in stats}


def _build_provider(
    provider_name: str,
    model_name: str,
    *,
    max_calls: int,
    environ: Mapping[str, str],
):
    budget = {"max_llm_calls_per_run": max_calls, "max_tokens_per_call": 256}
    config = {
        "budget": dict(budget),
        "cloudflare_models": [model_name] if model_name else [DEFAULT_CLOUDFLARE_MODEL],
    }
    return build_provider(
        config,
        budget,
        provider_name,
        model_name,
        environ=environ,
    )


def _call(provider: Any, messages: list[dict[str, str]], model_name: str) -> tuple[str | None, str | None, float]:
    started = time.monotonic()
    try:
        response, error = provider.chat(
            messages,
            temperature=0.0,
            max_tokens=128,
            model=model_name or None,
        )
    except Exception as exc:  # defensive: do not leak exception payloads
        response, error = None, f"provider_call_exception:{type(exc).__name__}"
    elapsed = round(max(0.0, time.monotonic() - started), 3)
    if not isinstance(response, str) or not response.strip():
        return None, _safe_error(error or "provider_returned_empty_response"), elapsed
    return response, None, elapsed


def _reject_constant(value: str) -> None:
    raise ValueError("nonstandard_json_constant")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _json_action_probe(response: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "invalid_json",
        "response_chars": len(response),
        "strict_json_valid": False,
        "action_schema_valid": False,
        "parse_error_code": "json_syntax_error",
    }
    try:
        value = json.loads(
            response,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return result
    result["strict_json_valid"] = True
    result["parse_error_code"] = None
    if (
        isinstance(value, dict)
        and set(value) == {"action", "tool", "arguments", "reason"}
        and value.get("action") == "tool_call"
        and value.get("tool") == "repository_summary"
        and value.get("arguments") == {}
        and isinstance(value.get("reason"), str)
        and bool(value["reason"].strip())
        and len(value["reason"]) <= 1000
    ):
        result["status"] = "passed"
        result["action_schema_valid"] = True
    else:
        result["status"] = "schema_mismatch"
    return result


def run_preflight(
    provider_name: str,
    model_name: str = "",
    *,
    environ: Mapping[str, str] | None = None,
    provider_builder: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Run a small provider-only preflight; injectable builder keeps tests offline."""
    env: Mapping[str, str] = os.environ if environ is None else environ
    model_name = model_name.strip() if isinstance(model_name, str) else ""
    report: dict[str, Any] = {
        "schema_version": "ae32c/provider-compatibility-preflight/v1",
        "provider": provider_name,
        "requested_model": model_name[:200],
        "effective_model": "provider-default-not-reported",
        "status": "not_run",
        "transport_probe": {"status": "not_run"},
        "json_action_probe": {"status": "not_applicable" if provider_name != "cloudflare" else "not_run"},
        "runtime_settings": {},
        "notes": [
            "No repository evidence tools are called by this preflight.",
            "The Cloudflare JSON action probe tests prompt-only output compatibility, not API-level constrained-output support.",
            "Raw model response bodies and provider credentials are not included in artifacts.",
        ],
    }
    if provider_name not in SUPPORTED_PROVIDERS:
        report.update(status="configuration_failed", error="unsupported_provider")
        return report
    if model_name and (len(model_name) > 200 or re.fullmatch(r"[A-Za-z0-9@._:/-]{1,200}", model_name) is None):
        report.update(status="configuration_failed", error="invalid_model_override")
        return report

    builder = provider_builder or _build_provider
    max_calls = 2 if provider_name == "cloudflare" else 1
    try:
        if provider_builder is None:
            provider = builder(
                provider_name,
                model_name,
                max_calls=max_calls,
                environ=env,
            )
        else:
            # Test seam: keep the production builder's signature out of fake fixtures.
            budget = {"max_llm_calls_per_run": max_calls, "max_tokens_per_call": 256}
            config = {
                "budget": dict(budget),
                "cloudflare_models": [model_name] if model_name else [DEFAULT_CLOUDFLARE_MODEL],
            }
            provider = builder(config, budget, provider_name, model_name, environ=env)
    except Exception as exc:
        report.update(status="configuration_failed", error=f"provider_initialization_failed:{type(exc).__name__}")
        return report

    effective_model = _effective_model(provider, model_name)
    report["effective_model"] = effective_model
    report["runtime_settings"] = _provider_runtime_settings(provider)

    baseline_messages = [
        {
            "role": "system",
            "content": "You are running a provider connectivity probe. Reply with exactly AE32C_PREFLIGHT_OK and no other text.",
        },
        {"role": "user", "content": "Reply exactly: AE32C_PREFLIGHT_OK"},
    ]
    baseline_response, baseline_error, baseline_elapsed = _call(provider, baseline_messages, model_name)
    transport = {
        "status": "completed" if baseline_response is not None else "provider_failed",
        "elapsed_seconds": baseline_elapsed,
        "response_chars": len(baseline_response) if baseline_response is not None else 0,
        "sentinel_match": baseline_response.strip() == BASELINE_SENTINEL if baseline_response is not None else False,
        "error": baseline_error or "",
    }
    report["transport_probe"] = transport
    report["runtime_settings"] = _provider_runtime_settings(provider)
    if baseline_response is None:
        report["status"] = "provider_failed"
        return report

    if provider_name != "cloudflare":
        report["status"] = "passed"
        report["notes"].append("A non-empty response was received; sentinel_match is informational and is not treated as a transport failure.")
        return report

    json_messages = [
        {
            "role": "system",
            "content": (
                "You are testing strict JSON action formatting. Return exactly one JSON object and no Markdown, "
                "fences, or surrounding prose. The object must have exactly these four keys: action, tool, "
                "arguments, reason. Set action to tool_call, tool to repository_summary, arguments to an empty "
                "object, and reason to a short non-empty string. This is a format probe only; no tool will execute."
            ),
        },
        {"role": "user", "content": "Return the required JSON action object now."},
    ]
    json_response, json_error, json_elapsed = _call(provider, json_messages, model_name)
    if json_response is None:
        report["json_action_probe"] = {
            "status": "provider_failed",
            "elapsed_seconds": json_elapsed,
            "response_chars": 0,
            "strict_json_valid": False,
            "action_schema_valid": False,
            "error": json_error or "provider_returned_empty_response",
        }
        report["runtime_settings"] = _provider_runtime_settings(provider)
        report["status"] = "json_probe_provider_failed"
        return report

    json_probe = _json_action_probe(json_response)
    json_probe["elapsed_seconds"] = json_elapsed
    json_probe["error"] = "" if json_probe["action_schema_valid"] else str(json_probe.get("parse_error_code") or json_probe["status"])
    report["json_action_probe"] = json_probe
    report["runtime_settings"] = _provider_runtime_settings(provider)
    report["status"] = "passed" if json_probe["action_schema_valid"] else "json_compatibility_failed"
    return report


def write_preflight_artifacts(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir = Path(output_dir)
    if output_dir.is_symlink() or not output_dir.exists() or not output_dir.is_dir():
        raise ValueError("output_directory_must_exist_and_must_not_be_symlink")
    output_resolved = output_dir.resolve(strict=True)
    checkout = Path.cwd().resolve()
    try:
        output_resolved.relative_to(checkout)
    except ValueError:
        pass
    else:
        raise ValueError("output_directory_must_be_outside_checkout")

    json_path = output_resolved / "preflight.json"
    markdown_path = output_resolved / "preflight.md"
    json_temp = output_resolved / ".preflight.json.tmp"
    markdown_temp = output_resolved / ".preflight.md.tmp"
    json_temp.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    lines = [
        "# AE-32C Provider Compatibility Preflight",
        "",
        f"- Provider: `{report.get('provider', 'unknown')}`",
        f"- Requested model: `{report.get('requested_model') or '(provider default)'}`",
        f"- Effective model: `{report.get('effective_model', 'unknown')}`",
        f"- Overall status: **{report.get('status', 'unknown')}**",
        f"- Transport probe: `{report.get('transport_probe', {}).get('status', 'unknown')}`",
        f"- Transport elapsed: {report.get('transport_probe', {}).get('elapsed_seconds', 'n/a')} seconds",
        f"- HTTP attempts: {report.get('runtime_settings', {}).get('http_attempts', 'not reported')}",
        f"- HTTP status counts: `{json.dumps(report.get('runtime_settings', {}).get('http_status_counts', {}), sort_keys=True)}`",
        f"- Effective timeout/retries: `{report.get('runtime_settings', {}).get('timeout_seconds', 'unknown')}s / {report.get('runtime_settings', {}).get('max_retries', 'unknown')}`",
    ]
    if report.get("provider") == "cloudflare":
        probe = report.get("json_action_probe", {})
        lines.extend([
            f"- JSON action probe: `{probe.get('status', 'unknown')}`",
            f"- Strict JSON valid: `{probe.get('strict_json_valid', False)}`",
            f"- Action schema valid: `{probe.get('action_schema_valid', False)}`",
            f"- JSON response characters: `{probe.get('response_chars', 0)}`",
        ])
    error = report.get("transport_probe", {}).get("error") or report.get("json_action_probe", {}).get("error") or report.get("error")
    if error:
        lines.extend(["", f"- Safe error: `{str(error)[:300]}`"])
    lines.extend(["", "No raw model response body or provider credential is included.", ""])
    markdown_temp.write_text("\n".join(lines), encoding="utf-8")
    json_temp.replace(json_path)
    markdown_temp.replace(markdown_path)
    return json_path, markdown_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a bounded AE-32C provider compatibility preflight without repository investigation.")
    parser.add_argument("--confirm-live-provider-calls", action="store_true", help="Required explicit consent for live provider requests.")
    parser.add_argument("--provider", choices=SUPPORTED_PROVIDERS, default=os.environ.get("FEA_LLM_PROVIDER", "cloudflare"))
    parser.add_argument("--model", default=os.environ.get("FEA_LLM_MODEL", ""), help="Optional model override; leave blank for provider default.")
    parser.add_argument("--output-dir", required=True, help="Existing output directory outside the source checkout.")
    args = parser.parse_args(argv)
    if not args.confirm_live_provider_calls:
        parser.error("live provider calls are disabled unless --confirm-live-provider-calls is supplied")

    output_dir = Path(args.output_dir)
    if output_dir.is_symlink() or not output_dir.exists() or not output_dir.is_dir():
        parser.error("--output-dir must be an existing non-symlink directory")
    try:
        output_dir.resolve(strict=True).relative_to(Path.cwd().resolve())
    except ValueError:
        pass
    else:
        parser.error("--output-dir must be outside the source checkout")

    report = run_preflight(args.provider, args.model)
    write_preflight_artifacts(report, output_dir)
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    if report.get("status") == "passed":
        return 0
    return 3 if str(report.get("status", "")).startswith("json_compatibility") else 2


if __name__ == "__main__":
    raise SystemExit(main())
