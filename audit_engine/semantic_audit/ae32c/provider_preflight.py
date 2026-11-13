"""Manual, bounded provider compatibility preflight for AE-32C.

This command makes no repository-tool calls and never executes the incident fixture.
It tests provider transport and one or more response representations. Native function
calls and API-enforced JSON are optional optimizations; provider-independent plain-text
responses are always tested and normalized locally against the canonical AE-32C protocol.

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
from providers.cloudflare import CLOUDFLARE_JSON_MODE_MODELS, QWEN_NATIVE_TOOL_MODEL
from providers.base import ProviderResponse, ProviderToolCall
from providers.safe_errors import sanitize_provider_error
from audit_engine.semantic_audit.ae32c.response_normalizer import (
    ResponseNormalizationError,
    normalize_provider_tool_call,
    normalize_provider_response,
)
from audit_engine.semantic_audit.ae32c.response_protocol import (
    RESPONSE_TOOL_NAME,
    build_response_tool_definition,
    response_tool_instruction,
    response_text_instruction,
)

DEFAULT_CLOUDFLARE_MODEL = "@cf/meta/llama-3.1-8b-instruct-fast"
BASELINE_SENTINEL = "AE32C_PREFLIGHT_OK"
CLOUDFLARE_NATIVE_TOOL_MODELS = frozenset({QWEN_NATIVE_TOOL_MODEL})
QWEN_NATIVE_TOOL_PROBE_MAX_TOKENS = 2048


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
        "structured_json_calls", "native_tool_call_requests",
        "native_tool_call_responses", "native_tool_call_failures",
        "last_http_status", "last_error_category", "last_error_codes",
        "last_request_id", "last_endpoint_mode", "last_finish_reason",
        "last_system_messages_coalesced", "last_message_compatibility",
        "native_tool_endpoint",
    )
    return {key: stats[key] for key in allowed if key in stats}


def _build_provider(
    provider_name: str,
    model_name: str,
    *,
    max_calls: int,
    environ: Mapping[str, str],
):
    probe_token_budget = (
        QWEN_NATIVE_TOOL_PROBE_MAX_TOKENS
        if provider_name == "cloudflare" and model_name == QWEN_NATIVE_TOOL_MODEL
        else 256
    )
    budget = {
        "max_llm_calls_per_run": max_calls,
        "max_tokens_per_call": probe_token_budget,
    }
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


def _call(
    provider: Any,
    messages: list[dict[str, str]],
    model_name: str,
    *,
    structured_json: bool = False,
    openai_compatible: bool = False,
) -> tuple[str | None, str | None, float]:
    started = time.monotonic()
    try:
        method = getattr(provider, "chat_structured", None) if structured_json else None
        if structured_json and not callable(method):
            response, error = None, "provider_structured_json_mode_unavailable"
        else:
            if openai_compatible:
                method = getattr(provider, "chat_openai_compatible", None)
                if not callable(method):
                    response, error = None, "provider_openai_compatible_chat_method_unavailable"
                else:
                    response, error = method(
                        messages,
                        temperature=0.0,
                        max_tokens=128,
                        model=model_name or None,
                    )
            else:
                method = method if callable(method) else provider.chat
                response, error = method(
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


def _native_tool_call_probe(
    provider: Any,
    model_name: str,
) -> dict[str, Any]:
    """Verify one Cloudflare-native virtual response function without dispatch."""
    method = getattr(provider, "chat_with_response_tool", None)
    if not callable(method):
        return {
            "status": "adapter_method_unavailable",
            "request_mode": "cloudflare_openai_compatible_chat_completions_auto_tool_choice",
            "tool_choice_policy": "auto",
            "function_name": RESPONSE_TOOL_NAME,
            "action_schema_valid": False,
            "error": "native_response_tool_method_unavailable",
        }

    messages = [
        {"role": "system", "content": response_tool_instruction()},
        {
            "role": "system",
            "content": (
                "This is a dry-run compatibility probe. Call the response function exactly once. "
                "Use action='tool_call', tool='repository_summary', arguments={}, provide a short "
                "non-empty reason, and set diagnosis={}. No repository tool will be executed."
            ),
        },
        {"role": "user", "content": "Submit the specified dry-run response now."},
    ]
    started = time.monotonic()
    try:
        response, error = method(
            messages,
            tool_definition=build_response_tool_definition(),
            temperature=0.0,
            max_tokens=QWEN_NATIVE_TOOL_PROBE_MAX_TOKENS,
            model=model_name or None,
        )
    except Exception as exc:
        response, error = None, f"provider_call_exception:{type(exc).__name__}"
    elapsed = round(max(0.0, time.monotonic() - started), 3)

    base = {
        "request_mode": "cloudflare_openai_compatible_chat_completions_auto_tool_choice",
        "tool_choice_policy": "auto",
        "function_name": RESPONSE_TOOL_NAME,
        "capability_basis": "cloudflare_qwen_function_calling_and_thinking_mode_tool_choice_constraints",
        "max_completion_tokens": QWEN_NATIVE_TOOL_PROBE_MAX_TOKENS,
        "elapsed_seconds": elapsed,
        "action_schema_valid": False,
        "tool_executed": False,
    }
    if isinstance(response, str):
        base.update({
            "status": "native_tool_call_not_returned",
            "response_type": "text",
            "response_chars": len(response),
            "error": "native_tool_call_not_returned",
        })
        return base
    if not isinstance(response, ProviderToolCall):
        base.update({
            "status": "provider_failed",
            "response_type": "unavailable",
            "response_chars": 0,
            "error": _safe_error(error or "provider_returned_no_native_tool_call"),
        })
        return base

    try:
        normalized = normalize_provider_tool_call(response)
    except ResponseNormalizationError as exc:
        base.update({
            "status": "invalid_native_tool_call",
            "response_type": "native_tool_call",
            "error": exc.code,
        })
        return base

    payload = normalized.payload
    valid = (
        set(payload) == {"action", "tool", "arguments", "reason"}
        and payload.get("action") == "tool_call"
        and payload.get("tool") == "repository_summary"
        and payload.get("arguments") == {}
        and isinstance(payload.get("reason"), str)
        and bool(payload["reason"].strip())
        and len(payload["reason"]) <= 1000
    )
    base.update({
        "status": "passed" if valid else "schema_mismatch",
        "response_type": "native_tool_call",
        "normalization_strategy": normalized.strategy,
        "canonical_action_valid": valid,
        "action_schema_valid": valid,
        "response_chars": len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))),
        "error": "" if valid else "canonical_action_schema_mismatch",
    })
    return base


def _text_response_probe(provider: Any, model_name: str) -> dict[str, Any]:
    """Test the provider-independent labelled text path without dispatching tools."""
    method = getattr(provider, "chat_text", None)
    if not callable(method):
        method = getattr(provider, "chat", None)
    base: dict[str, Any] = {
        "status": "not_run",
        "request_mode": "provider_plain_text_chat",
        "action_schema_valid": False,
        "tool_executed": False,
    }
    if not callable(method):
        base.update(status="adapter_method_unavailable", error="plain_text_chat_method_unavailable")
        return base

    messages = [
        {"role": "system", "content": response_text_instruction()},
        {
            "role": "system",
            "content": (
                "This is a provider-independent text-envelope probe. Do not use JSON mode "
                "or native function calling. Return exactly these labelled lines, one per line:\n"
                "ACTION: tool_call\nTOOL: search_repository\nARGUMENTS:\n"
                "query: AE32C_PREFLIGHT_QUERY\nmode: content\nmax_results: 3\n"
            ),
        },
        {"role": "user", "content": "Return the labelled text envelope now."},
    ]
    started = time.monotonic()
    try:
        response, error = method(
            messages,
            temperature=0.0,
            max_tokens=512,
            model=model_name or None,
        )
    except Exception as exc:
        response, error = None, f"provider_call_exception:{type(exc).__name__}"
    elapsed = round(max(0.0, time.monotonic() - started), 3)
    base["elapsed_seconds"] = elapsed
    if response is None:
        base.update(
            status="provider_failed",
            response_type="unavailable",
            response_chars=0,
            error=_safe_error(error or "provider_returned_no_response"),
        )
        # Report only bounded adapter-owned topology and error categories;
        # never persist prompts, provider error bodies, or credentials.
        try:
            stats = provider.get_stats()
            if isinstance(stats, dict):
                for source, target in (
                    ("last_endpoint_mode", "endpoint_mode"),
                    ("last_error_category", "error_category"),
                    ("last_message_compatibility", "message_compatibility"),
                    ("last_system_messages_coalesced", "system_messages_coalesced"),
                ):
                    if source in stats:
                        base[target] = stats[source]
        except Exception:
            pass
        return base

    response_type = (
        "provider_response" if hasattr(response, "tool_calls")
        else "native_tool_call" if isinstance(response, ProviderToolCall)
        else "text" if isinstance(response, str)
        else "unavailable"
    )
    try:
        normalized = normalize_provider_response(response, max_chars=20_000)
    except ResponseNormalizationError as exc:
        base.update(
            status="normalization_failed",
            response_type=response_type,
            response_chars=len(response) if isinstance(response, str) else 0,
            normalization_error=exc.code,
            error=exc.code,
        )
        return base

    payload = normalized.payload
    valid = (
        set(payload) == {"action", "tool", "arguments", "reason"}
        and payload.get("action") == "tool_call"
        and payload.get("tool") == "search_repository"
        and payload.get("arguments") == {
            "query": "AE32C_PREFLIGHT_QUERY",
            "mode": "content",
            "max_results": 3,
        }
        and isinstance(payload.get("reason"), str)
        and bool(payload["reason"].strip())
        and len(payload["reason"]) <= 1000
    )
    base.update(
        status="passed" if valid else "schema_mismatch",
        response_type=response_type,
        normalization_strategy=normalized.strategy,
        response_chars=(
            len(response) if isinstance(response, str)
            else len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        ),
        action_schema_valid=valid,
        error="" if valid else "canonical_action_schema_mismatch",
    )
    try:
        stats = provider.get_stats()
        if isinstance(stats, dict):
            base["endpoint_mode"] = stats.get("last_endpoint_mode")
            if "last_message_compatibility" in stats:
                base["message_compatibility"] = stats["last_message_compatibility"]
            if "last_system_messages_coalesced" in stats:
                base["system_messages_coalesced"] = stats["last_system_messages_coalesced"]
    except Exception:
        pass
    return base



def _negotiated_response_probe(provider: Any, model_name: str) -> dict[str, Any]:
    """Exercise endpoint negotiation with one inert canonical action (no repo tool)."""
    method = getattr(provider, "chat_negotiated", None)
    result: dict[str, Any] = {
        "status": "not_run", "tool_executed": False, "action_schema_valid": False,
        "request_mode": "provider_negotiated_response",
    }
    if not callable(method):
        result.update(status="adapter_method_unavailable", error="negotiated_chat_unavailable")
        return result
    messages = [
        {"role": "system", "content": (
            "This is an AE-32C endpoint compatibility probe. Return one canonical "
            "JSON action with exactly action, tool, arguments, reason, or if a "
            "strict schema/response function is provided, place the serialized "
            "action JSON in action_json. The action must be tool_call, the tool "
            "repository_summary, arguments {}, and a nonempty reason. This "
            "response is inspected locally; no repository tool will execute."
        )},
        {"role": "user", "content": "Provide the inert repository_summary action now."},
    ]
    started = time.monotonic()
    try:
        response, error = method(messages, temperature=0.0, max_tokens=512, model=model_name or None)
    except Exception as exc:
        response, error = None, f"provider_call_exception:{type(exc).__name__}"
    result["elapsed_seconds"] = round(max(0.0, time.monotonic() - started), 3)
    stats = {}
    try:
        candidate = provider.get_stats()
        if isinstance(candidate, dict):
            stats = candidate
    except Exception:
        pass
    mode = stats.get("response_strategy")
    if mode in {"json_schema", "native_tool_call", "json_object", "plain_text"}:
        result["request_mode"] = mode
    result["capability_source"] = str(stats.get("endpoint_capability_source", "unknown"))[:80]
    result["endpoint_capability_count"] = stats.get("endpoint_capability_count", 0)
    if response is None or error:
        result.update(status="provider_failed", error=_safe_error(error or "empty_response"))
        return result
    try:
        normalized = normalize_provider_response(response, max_chars=20_000)
    except ResponseNormalizationError as exc:
        result.update(status="normalization_failed", normalization_error=exc.code, error=exc.code)
        return result
    action = normalized.payload
    valid = (isinstance(action, dict) and set(action) == {"action", "tool", "arguments", "reason"}
        and action.get("action") == "tool_call" and action.get("tool") == "repository_summary"
        and action.get("arguments") == {} and isinstance(action.get("reason"), str)
        and bool(action["reason"].strip()) and len(action["reason"]) <= 1000)
    result.update(
        status="passed" if valid else "schema_mismatch",
        action_schema_valid=valid,
        normalization_strategy=normalized.strategy,
        response_type="native" if isinstance(response, (ProviderResponse, ProviderToolCall)) else "text",
        error="" if valid else "canonical_action_schema_mismatch",
    )
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
        "schema_version": "ae32c/provider-compatibility-preflight/v2",
        "provider": provider_name,
        "requested_model": model_name[:200],
        "effective_model": "provider-default-not-reported",
        "status": "not_run",
        "transport_probe": {"status": "not_run"},
        "json_action_probe": {
            "status": "not_applicable" if provider_name not in {"cloudflare", "openrouter"} else "not_run"
        },
        "native_tool_call_probe": {
            "status": "not_applicable"
        },
        "text_response_probe": {
            "status": "not_run"
        },
        "runtime_settings": {},
        "notes": [
            "No repository evidence tools are called by this preflight.",
            "Native function calling and provider-enforced JSON are optional response modes, not prerequisites for AE-32C.",
            "The plain-text response probe exercises the same provider-independent normalization contract used by the investigator; no repository tool is executed.",
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
    max_calls = 3 if provider_name in {"cloudflare", "openrouter"} else 2
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
            probe_token_budget = (
                QWEN_NATIVE_TOOL_PROBE_MAX_TOKENS
                if provider_name == "cloudflare" and model_name == QWEN_NATIVE_TOOL_MODEL
                else 256
            )
            budget = {
                "max_llm_calls_per_run": max_calls,
                "max_tokens_per_call": probe_token_budget,
            }
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
    qwen_native_model = (
        provider_name == "cloudflare" and effective_model in CLOUDFLARE_NATIVE_TOOL_MODELS
    )
    baseline_response, baseline_error, baseline_elapsed = _call(
        provider,
        baseline_messages,
        model_name,
        openai_compatible=qwen_native_model,
    )
    transport = {
        "status": "completed" if baseline_response is not None else "provider_failed",
        "request_mode": (
            "cloudflare_openai_compatible_chat_completions"
            if qwen_native_model else "provider_default_chat"
        ),
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

    if provider_name == "nararouter":
        text_probe = _text_response_probe(provider, effective_model)
        report["text_response_probe"] = text_probe
        text_ok = text_probe.get("status") == "passed"
        report["usable_response_modes"] = ["plain_text_envelope"] if text_ok else []
        report["response_mode_status"] = "text_fallback_only" if text_ok else "no_usable_response_mode"
        report["status"] = "passed" if text_ok else "response_compatibility_failed"
        report["notes"].append(
            "NaraRouter is evaluated through the same provider-independent plain-text response contract; "
            "no repository tool is executed during this probe."
        )
        report["runtime_settings"] = _provider_runtime_settings(provider)
        return report

    if provider_name == "cloudflare" and effective_model in CLOUDFLARE_NATIVE_TOOL_MODELS:
        report["json_action_probe"] = {
            "status": "not_applicable_optional_mode",
            "request_mode": "not_requested",
            "strict_json_valid": False,
            "action_schema_valid": False,
        }
        native_probe = _native_tool_call_probe(provider, effective_model)
        text_probe = _text_response_probe(provider, effective_model)
        report["native_tool_call_probe"] = native_probe
        report["text_response_probe"] = text_probe
        native_ok = native_probe.get("status") == "passed"
        text_ok = text_probe.get("status") == "passed"
        report["usable_response_modes"] = [
            mode for mode, ok in (
                ("native_tool_call", native_ok),
                ("plain_text_envelope", text_ok),
            ) if ok
        ]
        report["response_mode_status"] = (
            "native_and_text"
            if native_ok and text_ok
            else "native_only"
            if native_ok
            else "text_fallback_only"
            if text_ok
            else "no_usable_response_mode"
        )
        report["runtime_settings"] = _provider_runtime_settings(provider)
        report["status"] = "passed" if native_ok or text_ok else "response_compatibility_failed"
        return report

    # One negotiated probe replaces the legacy JSON-only probe for modern
    # adapters; total live model requests remain unchanged. Metadata requests
    # are bounded separately and contain only the selected model ID.
    if (getattr(provider, "supports_negotiated_responses", False) is True
        and callable(getattr(provider, "chat_negotiated", None))):
        negotiated_probe = _negotiated_response_probe(provider, effective_model)
        text_probe = _text_response_probe(provider, effective_model)
        report["negotiated_response_probe"] = negotiated_probe
        report["json_action_probe"] = {
            "status": "superseded_by_negotiated_probe",
            "request_mode": "not_requested",
            "action_schema_valid": False,
        }
        report["text_response_probe"] = text_probe
        negotiated_ok = negotiated_probe.get("status") == "passed"
        text_ok = text_probe.get("status") == "passed"
        report["usable_response_modes"] = [
            mode for mode, ok in (
                ("negotiated_response", negotiated_ok),
                ("plain_text_envelope", text_ok),
            ) if ok
        ]
        report["response_mode_status"] = (
            "negotiated_and_text" if negotiated_ok and text_ok
            else "negotiated_only" if negotiated_ok
            else "text_fallback_only" if text_ok
            else "no_usable_response_mode"
        )
        report["status"] = "passed" if negotiated_ok or text_ok else "response_compatibility_failed"
        report["runtime_settings"] = _provider_runtime_settings(provider)
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
    # Model capabilities differ within a provider. Cloudflare's published
    # JSON Mode list does not include Qwen 3.8 27B, so Qwen must use ordinary
    # chat and strict local JSON/action-schema validation. Do not infer JSON
    # Mode support from the generic presence of a response_format parameter.
    use_api_json_mode = (
        provider_name == "cloudflare"
        and effective_model in CLOUDFLARE_JSON_MODE_MODELS
    )
    json_response, json_error, json_elapsed = _call(
        provider, json_messages, model_name, structured_json=use_api_json_mode
    )
    if json_response is None:
        json_probe = {
            "status": "provider_failed",
            "request_mode": (
                "api_response_format_json_object"
                if use_api_json_mode and callable(getattr(provider, "chat_structured", None))
                else "plain_chat_local_json_validation"
                if provider_name in {"cloudflare", "openrouter"}
                else "unavailable"
            ),
            "elapsed_seconds": json_elapsed,
            "response_chars": 0,
            "strict_json_valid": False,
            "action_schema_valid": False,
            "capability_basis": (
                "cloudflare_published_json_mode_model_allowlist"
                if use_api_json_mode
                else "model_not_confirmed_for_api_json_mode"
            ),
            "error": json_error or "provider_returned_empty_response",
        }
    else:
        json_probe = _json_action_probe(json_response)
        json_probe["request_mode"] = (
            "api_response_format_json_object"
            if use_api_json_mode
            else "plain_chat_local_json_validation"
        )
        json_probe["capability_basis"] = (
            "cloudflare_published_json_mode_model_allowlist"
            if use_api_json_mode
            else "model_not_confirmed_for_api_json_mode"
        )
        json_probe["elapsed_seconds"] = json_elapsed
        json_probe["error"] = "" if json_probe["action_schema_valid"] else str(
            json_probe.get("parse_error_code") or json_probe["status"]
        )
    report["json_action_probe"] = json_probe

    text_probe = _text_response_probe(provider, effective_model)
    report["text_response_probe"] = text_probe
    json_ok = json_probe.get("action_schema_valid") is True
    text_ok = text_probe.get("action_schema_valid") is True
    report["usable_response_modes"] = [
        mode for mode, ok in (
            ("json_action", json_ok),
            ("plain_text_envelope", text_ok),
        ) if ok
    ]
    report["response_mode_status"] = (
        "json_and_text"
        if json_ok and text_ok
        else "json_only"
        if json_ok
        else "text_fallback_only"
        if text_ok
        else "no_usable_response_mode"
    )
    report["runtime_settings"] = _provider_runtime_settings(provider)
    report["status"] = "passed" if json_ok or text_ok else (
        "json_probe_provider_failed"
        if json_probe.get("status") == "provider_failed"
        else "json_compatibility_failed"
    )
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
        f"- Transport request mode: `{report.get('transport_probe', {}).get('request_mode', 'provider_default_chat')}`",
        f"- Transport elapsed: {report.get('transport_probe', {}).get('elapsed_seconds', 'n/a')} seconds",
        f"- HTTP attempts: {report.get('runtime_settings', {}).get('http_attempts', 'not reported')}",
        f"- HTTP status counts: `{json.dumps(report.get('runtime_settings', {}).get('http_status_counts', {}), sort_keys=True)}`",
        f"- Effective timeout/retries: `{report.get('runtime_settings', {}).get('timeout_seconds', 'unknown')}s / {report.get('runtime_settings', {}).get('max_retries', 'unknown')}`",
    ]
    if report.get("provider") in {"cloudflare", "openrouter"}:
        probe = report.get("json_action_probe", {})
        lines.extend([
            f"- JSON action probe: `{probe.get('status', 'unknown')}`",
            f"- Request mode: `{probe.get('request_mode', 'not_confirmed')}`",
            f"- Strict JSON valid: `{probe.get('strict_json_valid', False)}`",
            f"- Action schema valid: `{probe.get('action_schema_valid', False)}`",
            f"- JSON response characters: `{probe.get('response_chars', 0)}`",
        ])
        native_probe = report.get("native_tool_call_probe", {})
        if native_probe.get("status") != "not_applicable":
            lines.extend([
                f"- Native response-tool probe: `{native_probe.get('status', 'unknown')}`",
                f"- Native request mode: `{native_probe.get('request_mode', 'not_confirmed')}`",
                f"- Native max completion tokens: `{native_probe.get('max_completion_tokens', 'not_reported')}`",
                f"- Function name: `{native_probe.get('function_name', 'unknown')}`",
                f"- Canonical action valid: `{native_probe.get('canonical_action_valid', native_probe.get('action_schema_valid', False))}`",
                f"- Tool executed: `{native_probe.get('tool_executed', False)}`",
            ])
    text_probe = report.get("text_response_probe", {})
    if text_probe.get("status") != "not_run":
        lines.extend([
            f"- Plain-text response probe: `{text_probe.get('status', 'unknown')}`",
            f"- Text normalization strategy: `{text_probe.get('normalization_strategy', 'not_reported')}`",
            f"- Text action schema valid: `{text_probe.get('action_schema_valid', False)}`",
            f"- Usable response modes: `{', '.join(report.get('usable_response_modes', [])) or 'none'}`",
        ])
    error = (
        report.get("transport_probe", {}).get("error")
        or report.get("json_action_probe", {}).get("error")
        or report.get("native_tool_call_probe", {}).get("error")
        or report.get("text_response_probe", {}).get("error")
        or report.get("error")
    )
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
