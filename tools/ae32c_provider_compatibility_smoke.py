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

ACTION_TOP_LEVEL_KEYS = {"action", "diagnosis"}
DIAGNOSIS_KEYS = {
    "summary", "root_cause", "claims", "proposed_corrective_action", "limitations", "next_steps"
}
ROOT_CAUSE_KEYS = {"statement", "confidence", "evidence_refs", "source_references"}
CLAIM_KEYS = {"statement", "kind", "confidence", "evidence_refs", "source_references"}
SOURCE_REFERENCE_KEYS = {"evidence_id", "path", "line", "source_sha256"}
CONFIDENCE_VALUES = {"low", "medium", "high"}
CLAIM_KIND_VALUES = {"observation", "hypothesis", "conclusion", "limitation", "recommendation"}


def _string_list(value: object, *, nonempty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (not nonempty or bool(value))
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
    )


def _source_reference_list_shape(value: object) -> bool:
    if not isinstance(value, list) or len(value) > 20:
        return False
    for item in value:
        if not isinstance(item, dict) or set(item) != SOURCE_REFERENCE_KEYS:
            return False
        if not isinstance(item.get("evidence_id"), str) or not item["evidence_id"]:
            return False
        if not isinstance(item.get("path"), str) or not item["path"]:
            return False
        line = item.get("line")
        if isinstance(line, bool) or not isinstance(line, int) or line < 1:
            return False
        digest = item.get("source_sha256")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            return False
    return True


def _action_schema_diagnostics(response: str) -> dict[str, Any]:
    """Check response syntax and AE-32C final-action shape, never evidence truth."""
    result: dict[str, Any] = {
        "json_parse_success": False,
        "schema_shape_valid": False,
        "schema_errors": [],
        "top_level_keys_exact": False,
        "action_final": False,
        "diagnosis_keys_exact": False,
        "root_cause_keys_exact": False,
        "claim_count": 0,
        "claim_shapes_valid": False,
        "required_value_types_valid": False,
        "source_reference_items_shape_valid": False,
        "synthetic_evidence_ids_only": True,
        "semantic_evidence_validation_performed": False,
        "source_reference_resolution_performed": False,
    }
    try:
        value = json.loads(response)
    except (json.JSONDecodeError, TypeError):
        result["schema_errors"] = ["invalid_json_syntax"]
        result["json_error_category"] = "invalid_json_syntax"
        if isinstance(response, str):
            try:
                json.loads(response)
            except json.JSONDecodeError as exc:
                result["json_error_line"] = int(exc.lineno)
                result["json_error_column"] = int(exc.colno)
        return result

    result["json_parse_success"] = True
    errors: list[str] = []
    if not isinstance(value, dict):
        errors.append("top_level_not_object")
        result["schema_errors"] = errors
        return result

    result["top_level_keys_exact"] = set(value) == ACTION_TOP_LEVEL_KEYS
    if not result["top_level_keys_exact"]:
        errors.append("top_level_keys_invalid")
    result["action_final"] = value.get("action") == "final"
    if not result["action_final"]:
        errors.append("action_not_final")

    diagnosis = value.get("diagnosis")
    if not isinstance(diagnosis, dict):
        errors.append("diagnosis_not_object")
        result["schema_errors"] = sorted(set(errors))
        return result

    result["diagnosis_keys_exact"] = set(diagnosis) == DIAGNOSIS_KEYS
    if not result["diagnosis_keys_exact"]:
        errors.append("diagnosis_keys_invalid")

    root = diagnosis.get("root_cause")
    if not isinstance(root, dict):
        errors.append("root_cause_not_object")
        root = {}
    result["root_cause_keys_exact"] = set(root) == ROOT_CAUSE_KEYS
    if not result["root_cause_keys_exact"]:
        errors.append("root_cause_keys_invalid")

    claims = diagnosis.get("claims")
    result["claim_count"] = len(claims) if isinstance(claims, list) else 0
    claim_shapes_valid = (
        isinstance(claims, list)
        and 1 <= len(claims) <= 20
        and all(isinstance(claim, dict) and set(claim) == CLAIM_KEYS for claim in claims)
    )
    result["claim_shapes_valid"] = bool(claim_shapes_valid)
    if not claim_shapes_valid:
        errors.append("claim_shapes_invalid")

    source_lists_valid = (
        _source_reference_list_shape(root.get("source_references"))
        and isinstance(claims, list)
        and all(isinstance(claim, dict) for claim in claims)
        and all(_source_reference_list_shape(claim.get("source_references")) for claim in claims)
    )
    result["source_reference_items_shape_valid"] = bool(source_lists_valid)
    if not source_lists_valid:
        errors.append("source_reference_shape_invalid")

    root_values_valid = (
        isinstance(root.get("statement"), str) and bool(root["statement"].strip())
        and root.get("confidence") in CONFIDENCE_VALUES
        and _string_list(root.get("evidence_refs"), nonempty=True)
        and _source_reference_list_shape(root.get("source_references"))
    )
    claim_values_valid = bool(claim_shapes_valid) and all(
        isinstance(claim.get("statement"), str) and bool(claim["statement"].strip())
        and claim.get("kind") in CLAIM_KIND_VALUES
        and claim.get("confidence") in CONFIDENCE_VALUES
        and _string_list(claim.get("evidence_refs"), nonempty=True)
        and _source_reference_list_shape(claim.get("source_references"))
        for claim in claims
    )
    diagnosis_values_valid = (
        isinstance(diagnosis.get("summary"), str) and bool(diagnosis["summary"].strip())
        and isinstance(diagnosis.get("proposed_corrective_action"), str)
        and isinstance(diagnosis.get("limitations"), list)
        and all(isinstance(item, str) for item in diagnosis["limitations"])
        and isinstance(diagnosis.get("next_steps"), list)
        and all(isinstance(item, str) for item in diagnosis["next_steps"])
    )
    result["required_value_types_valid"] = bool(root_values_valid and claim_values_valid and diagnosis_values_valid)
    if not result["required_value_types_valid"]:
        errors.append("required_value_types_invalid")

    result["schema_errors"] = sorted(set(errors))
    result["schema_shape_valid"] = not errors
    return result


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
    parser.add_argument(
        "--request-profile", choices=("marker", "ae32c_final_action"), default="marker",
        help="Probe a tiny marker object or the representative AE-32C final-action response shape.",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=None,
        help="Bounded output budget (128-2048); defaults to 128 for marker and 768 for action-schema profile.",
    )
    args = parser.parse_args(argv)
    if args.provider not in SUPPORTED_PROVIDERS:
        parser.error("--provider must select a supported provider")
    if not args.confirm_live_provider_calls:
        parser.error("one live provider request is disabled unless --confirm-live-provider-calls is supplied")
    requested_model = args.model.strip()
    if requested_model and MODEL_PATTERN.fullmatch(requested_model) is None:
        parser.error("--model must be at most 200 characters and use only letters, digits, @, ., _, :, /, or -")

    if args.request_profile == "ae32c_final_action" and args.request_mode != "json_object":
        parser.error("--request-profile ae32c_final_action requires --request-mode json_object")
    default_max_tokens = 768 if args.request_profile == "ae32c_final_action" else 128
    max_tokens = default_max_tokens if args.max_tokens is None else args.max_tokens
    if isinstance(max_tokens, bool) or not 128 <= max_tokens <= 2048:
        parser.error("--max-tokens must be between 128 and 2048")

    provider_name = args.provider.strip().lower()
    model_name = requested_model or (
        CLOUDFLARE_DEFAULT_MODEL if provider_name == "cloudflare" else DEFAULT_MODELS[provider_name]
    )
    budget = {"max_llm_calls_per_run": 1, "max_tokens_per_call": max_tokens}
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
            "request_profile": args.request_profile,
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

    if args.request_profile == "ae32c_final_action":
        messages = [
            {
                "role": "system",
                "content": (
                    "Return exactly one JSON object, with no Markdown or surrounding prose. "
                    "It must use the AE-32C final-action shape: top-level keys exactly action and diagnosis; "
                    "action must be final; diagnosis keys exactly summary, root_cause, claims, "
                    "proposed_corrective_action, limitations, next_steps; root_cause keys exactly "
                    "statement, confidence, evidence_refs, source_references; each claim keys exactly "
                    "statement, kind, confidence, evidence_refs, source_references. Confidence is low, "
                    "medium, or high. Claim kind is observation, hypothesis, conclusion, limitation, "
                    "or recommendation. Use one synthetic evidence ID E0001 in evidence_refs and empty "
                    "source_references arrays. Do not invent source paths or citations. This is only a "
                    "format probe; no repository evidence was examined and no real diagnosis is requested."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Produce the smallest complete AE-32C final-action JSON object. Include one concise "
                    "claim, a short summary and root-cause statement, a proposed corrective action, one "
                    "limitation, and one next step. Use only synthetic evidence ID E0001; use empty "
                    "source_references arrays. Do not add keys."
                ),
            },
        ]
    elif args.request_mode == "json_object":
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
        call_kwargs = {"temperature": 0.0, "max_tokens": max_tokens, "model": model_name}
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
        action_schema = None
        if received and args.request_mode == "json_object":
            try:
                parsed_response = json.loads(response)
                response_is_json_object = isinstance(parsed_response, dict)
                if args.request_profile == "ae32c_final_action":
                    action_schema = _action_schema_diagnostics(response)
                else:
                    response_marker_match = bool(
                        response_is_json_object and parsed_response.get("marker") == "AE32_SMOKE_OK"
                    )
            except (json.JSONDecodeError, TypeError):
                response_is_json_object = False
                if args.request_profile == "ae32c_final_action":
                    action_schema = _action_schema_diagnostics(response)
        elif received:
            response_marker_match = response.strip() == "AE32_SMOKE_OK"

        structured_json_calls = stats.get("structured_json_calls", 0)
        if isinstance(structured_json_calls, bool) or not isinstance(structured_json_calls, int) or not 0 <= structured_json_calls <= 1:
            structured_json_calls = 0
        if not received:
            status = "provider_rejected_or_failed"
        elif args.request_profile == "ae32c_final_action":
            status = (
                "action_schema_shape_valid"
                if action_schema and action_schema.get("schema_shape_valid") is True
                else "action_schema_shape_invalid"
            )
        else:
            status = "completion_received"

        payload = {
            "schema_version": "ae32c/provider-compatibility-smoke/v1",
            "provider": provider_name,
            "model": model_name,
            "status": status,
            "request_mode": args.request_mode,
            "request_profile": args.request_profile,
            "max_tokens_requested": max_tokens,
            "response_format_requested": args.request_mode == "json_object",
            "capability_declared": capability_declared,
            "response_received": received,
            "response_is_json_object": response_is_json_object if args.request_mode == "json_object" else None,
            "response_marker_match": response_marker_match if args.request_profile == "marker" else None,
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
        if action_schema is not None:
            payload.update(action_schema)
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
            "request_profile": args.request_profile,
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
