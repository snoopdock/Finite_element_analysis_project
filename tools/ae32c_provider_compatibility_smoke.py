#!/usr/bin/env python3
"""One-request, opt-in provider compatibility diagnostic for AE-32C.

This command does not inspect a repository or run an investigation. It makes at
most one chat-completion call and prints only safe structural diagnostics. It is
intended to diagnose endpoint/model/request compatibility after G9.42 passes.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Mapping

from providers.factory import SUPPORTED_PROVIDERS, build_provider
from providers.openai_compatible import DEFAULT_MODELS

CLOUDFLARE_DEFAULT_MODEL = "@cf/meta/llama-3.1-8b-instruct-fast"
MODEL_PATTERN = re.compile(r"[A-Za-z0-9@._:/-]{1,200}")
SAFE_DIAGNOSTIC_FIELDS = {
    "http_status", "body_status", "body_shape", "error_shape",
    "error_type", "error_code", "error_param", "error_fields", "top_level_error_fields",
    "error_message_category", "error_request_id",
}
SAFE_FIELD_NAMES = {"type", "code", "param", "message", "details", "metadata", "status", "request_id", "trace_id"}


def _safe_diagnostics(stats: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    error_code = stats.get("last_error_code")
    if isinstance(error_code, str) and len(error_code) <= 100 and re.fullmatch(r"[A-Za-z0-9_.:-]+", error_code):
        result["last_error_code"] = error_code
    status = stats.get("last_http_status")
    if isinstance(status, int) and not isinstance(status, bool) and 100 <= status <= 599:
        result["last_http_status"] = status
    attempts = stats.get("http_attempts")
    if isinstance(attempts, int) and not isinstance(attempts, bool) and 0 <= attempts <= 10:
        result["http_attempts"] = attempts
    http_error = stats.get("last_http_error_diagnostic")
    if isinstance(http_error, Mapping):
        safe: dict[str, Any] = {}
        for key in SAFE_DIAGNOSTIC_FIELDS:
            value = http_error.get(key)
            if key in {"error_fields", "top_level_error_fields"}:
                if isinstance(value, list):
                    safe[key] = [item for item in value[:12] if isinstance(item, str) and item in SAFE_FIELD_NAMES]
            elif key == "http_status":
                if isinstance(value, int) and not isinstance(value, bool) and 100 <= value <= 599:
                    safe[key] = value
            elif isinstance(value, str) and len(value) <= 100 and re.fullmatch(r"[A-Za-z0-9_.:/\-\[\]]+|present_unclassified", value):
                safe[key] = value
        if safe:
            result["last_http_error_diagnostic"] = safe
    envelope = stats.get("last_envelope_diagnostic")
    if isinstance(envelope, Mapping):
        safe_envelope = {}
        for key in ("envelope_kind", "choices_shape"):
            value = envelope.get(key)
            if isinstance(value, str) and value in {
                "standard_choices", "upstream_error_object", "alternate_wrapper", "unrecognized_object",
                "non_object", "nonempty_list", "empty_list", "absent", "wrong_type",
            }:
                safe_envelope[key] = value
        if isinstance(envelope.get("has_error_object"), bool):
            safe_envelope["has_error_object"] = envelope["has_error_object"]
        if safe_envelope:
            result["last_envelope_diagnostic"] = safe_envelope
    usage = stats.get("usage")
    if isinstance(usage, Mapping):
        safe_usage = {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens", "reported_cost_usd"):
            value = usage.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
                safe_usage[key] = round(float(value), 8) if key == "reported_cost_usd" else int(value)
        if safe_usage:
            result["usage"] = safe_usage
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Make exactly one explicitly authorized provider compatibility request.")
    parser.add_argument("--confirm-live-provider-calls", action="store_true",
                        help="Required explicit authorization for one live provider request.")
    parser.add_argument("--provider", choices=SUPPORTED_PROVIDERS,
                        default=os.environ.get("FEA_LLM_PROVIDER", "nararouter"))
    parser.add_argument("--model", default=os.environ.get("FEA_LLM_MODEL", ""))
    parser.add_argument(
        "--request-mode", choices=("plain", "json_object"), default="plain",
        help="Use a plain marker request or explicitly probe API-enforced JSON-object mode.",
    )
    args = parser.parse_args(argv)
    if args.provider not in SUPPORTED_PROVIDERS:
        parser.error("--provider must select a supported provider")
    if not args.confirm_live_provider_calls:
        parser.error("one live provider request is disabled unless --confirm-live-provider-calls is supplied")
    requested_model = args.model.strip()
    if requested_model and MODEL_PATTERN.fullmatch(requested_model) is None:
        parser.error("--model must be at most 200 characters and use only letters, digits, @, ., _, :, /, or -")

    provider_name = args.provider.strip().lower()
    model_name = requested_model or (
        CLOUDFLARE_DEFAULT_MODEL if provider_name == "cloudflare" else DEFAULT_MODELS[provider_name]
    )
    budget = {"max_llm_calls_per_run": 1, "max_tokens_per_call": 128}
    config = {"budget": dict(budget), "cloudflare_models": [model_name]}
    try:
        provider = build_provider(config, budget, provider_name, model_name, environ=os.environ)
    except Exception as exc:
        print(json.dumps({
            "schema_version": "ae32c/provider-compatibility-smoke/v1",
            "provider": provider_name,
            "model": model_name,
            "status": "configuration_failed",
            "error_type": type(exc).__name__,
            "live_provider_calls_made": False,
        }, sort_keys=True, indent=2, allow_nan=False))
        return 0

    # The diagnostic is intentionally one logical call and one HTTP attempt,
    # not a retry experiment. JSON-object mode is opt-in for this probe only.
    if hasattr(provider, "max_retries"):
        try:
            provider.max_retries = 1
        except Exception:
            pass

    capability_declared = False
    if hasattr(provider, "get_capabilities"):
        try:
            capabilities = provider.get_capabilities()
            capability_declared = isinstance(capabilities, Mapping) and capabilities.get("json_object_mode") is True
        except Exception:
            capability_declared = False

    if args.request_mode == "json_object" and not capability_declared:
        print(json.dumps({
            "schema_version": "ae32c/provider-compatibility-smoke/v1",
            "provider": provider_name,
            "model": model_name,
            "status": "capability_not_declared",
            "request_mode": args.request_mode,
            "response_format_requested": False,
            "capability_declared": False,
            "request_count_limit": 1,
            "logical_calls_reported": 0,
            "http_attempts_reported": 0,
            "live_provider_calls_made": False,
            "raw_response_logged": False,
            "raw_error_body_logged": False,
        }, sort_keys=True, indent=2, allow_nan=False))
        return 0

    if args.request_mode == "json_object":
        messages = [
            {"role": "system", "content": 'Return exactly one JSON object with one key "marker" and string value "AE32_SMOKE_OK". Do not use markdown or additional keys.'},
            {"role": "user", "content": 'Return the JSON object: {"marker":"AE32_SMOKE_OK"}.'},
        ]
    else:
        messages = [
            {"role": "system", "content": "Return exactly the marker AE32_SMOKE_OK and no other text."},
            {"role": "user", "content": "Reply with AE32_SMOKE_OK."},
        ]

    stats: Mapping[str, Any] = {}
    try:
        call_kwargs = {"temperature": 0.0, "max_tokens": 128, "model": model_name}
        if args.request_mode == "json_object":
            call_kwargs["response_format"] = {"type": "json_object"}
        response, error = provider.chat(messages, **call_kwargs)
        raw_stats = provider.get_stats()
        stats = raw_stats if isinstance(raw_stats, Mapping) else {}
        received = isinstance(response, str) and bool(response.strip()) and not error
        logical_calls = stats.get("logical_calls", stats.get("total_calls", 1))
        if isinstance(logical_calls, bool) or not isinstance(logical_calls, int) or not 0 <= logical_calls <= 10:
            logical_calls = 1
        http_attempts = stats.get("http_attempts", 1)
        if isinstance(http_attempts, bool) or not isinstance(http_attempts, int) or not 0 <= http_attempts <= 10:
            http_attempts = 1
        response_is_json_object = False
        response_marker_match = False
        if received and args.request_mode == "json_object":
            try:
                parsed_response = json.loads(response)
                response_is_json_object = isinstance(parsed_response, dict)
                response_marker_match = bool(
                    response_is_json_object and parsed_response.get("marker") == "AE32_SMOKE_OK"
                )
            except (json.JSONDecodeError, TypeError):
                response_is_json_object = False
        elif received:
            response_marker_match = response.strip() == "AE32_SMOKE_OK"

        structured_json_calls = stats.get("structured_json_calls", 0)
        if isinstance(structured_json_calls, bool) or not isinstance(structured_json_calls, int) or not 0 <= structured_json_calls <= 1:
            structured_json_calls = 0
        payload = {
            "schema_version": "ae32c/provider-compatibility-smoke/v1",
            "provider": provider_name,
            "model": model_name,
            "status": "completion_received" if received else "provider_rejected_or_failed",
            "request_mode": args.request_mode,
            "response_format_requested": args.request_mode == "json_object",
            "capability_declared": capability_declared,
            "response_received": received,
            "response_is_json_object": response_is_json_object if args.request_mode == "json_object" else None,
            "response_marker_match": response_marker_match,
            "response_chars": len(response) if isinstance(response, str) else 0,
            "request_count_limit": 1,
            "logical_calls_reported": logical_calls,
            "http_attempts_reported": http_attempts,
            "structured_json_calls": structured_json_calls,
            "live_provider_calls_made": True,
            "raw_response_logged": False,
            "raw_error_body_logged": False,
            "diagnostics": _safe_diagnostics(stats),
        }
    except Exception as exc:
        try:
            raw_stats = provider.get_stats()
            stats = raw_stats if isinstance(raw_stats, Mapping) else stats
        except Exception:
            pass
        logical_calls = stats.get("logical_calls", stats.get("total_calls", 1))
        if isinstance(logical_calls, bool) or not isinstance(logical_calls, int) or not 0 <= logical_calls <= 10:
            logical_calls = 1
        http_attempts = stats.get("http_attempts", 1)
        if isinstance(http_attempts, bool) or not isinstance(http_attempts, int) or not 0 <= http_attempts <= 10:
            http_attempts = 1
        payload = {
            "schema_version": "ae32c/provider-compatibility-smoke/v1",
            "provider": provider_name,
            "model": model_name,
            "status": "adapter_exception",
            "request_mode": args.request_mode,
            "response_format_requested": args.request_mode == "json_object",
            "capability_declared": capability_declared,
            "error_type": type(exc).__name__,
            "request_count_limit": 1,
            "logical_calls_reported": logical_calls,
            "http_attempts_reported": http_attempts,
            "live_provider_calls_made": True,
            "raw_response_logged": False,
            "raw_error_body_logged": False,
            "diagnostics": _safe_diagnostics(stats),
        }
    print(json.dumps(payload, sort_keys=True, indent=2, allow_nan=False))
    # The process reports whether the diagnostic ran; provider failure is the
    # measured outcome, not a reason to discard the diagnostic JSON.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
