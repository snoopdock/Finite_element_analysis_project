"""Conservative provider-adapter capability declarations.

Capabilities describe what the local adapter deliberately exposes, not a
guarantee that every selected model will follow the requested format. Model
behavior and response validity must still be checked locally.
"""
from __future__ import annotations

from typing import Any, Mapping

_CAPABILITY_KEYS = (
    "json_object_mode",
    "json_schema_mode",
    "native_tool_calls",
    "finish_reason_reporting",
    "plain_text_mode",
)


def get_provider_capabilities(
    provider: Any,
    *,
    provider_name: str = "",
    model_name: str = "",
) -> dict[str, Any]:
    """Return normalized, fail-closed capabilities for one adapter/model pair.

    Unknown capabilities are false. Model-specific support is not inferred from
    a provider brand or an OpenAI-compatible endpoint.
    """
    declared: Mapping[str, Any] = {}
    getter = getattr(provider, "get_capabilities", None)
    if callable(getter):
        try:
            candidate = getter()
            if isinstance(candidate, Mapping):
                declared = candidate
        except Exception:
            declared = {}
    capabilities = {
        key: declared.get(key) is True
        for key in _CAPABILITY_KEYS
    }
    # Plain text is the universal compatibility floor. It is exposed whenever
    # the adapter has a chat entry point; no provider/model JSON or tool-call
    # capability is inferred from it.
    capabilities["plain_text_mode"] = bool(
        capabilities["plain_text_mode"]
        or callable(getattr(provider, "chat_text", None))
        or callable(getattr(provider, "chat", None))
    )
    return {
        "schema_version": "provider-capabilities/v1",
        "provider": str(provider_name or getattr(provider, "provider_name", "") or "unknown")[:100],
        "model": str(model_name or getattr(provider, "model", "") or "provider-default-not-reported")[:200],
        "scope": "adapter_declared_not_model_behavior_verified",
        "capabilities": capabilities,
    }



def should_fallback_to_plain_text(provider: Any) -> bool:
    """Return true only for a non-transient structured-request rejection.

    A fallback is not a general retry. Authentication, quota, rate-limit,
    transport, timeout, and server failures must remain failures. The helper
    uses adapter telemetry rather than guessing from provider error prose.
    """
    getter = getattr(provider, "get_stats", None)
    if not callable(getter):
        return False
    try:
        stats = getter()
    except Exception:
        return False
    if not isinstance(stats, Mapping):
        return False
    status = stats.get("last_http_status")
    diagnostic = stats.get("last_http_error_diagnostic")
    if not isinstance(status, int) and isinstance(diagnostic, Mapping):
        status = diagnostic.get("http_status")
    if isinstance(status, bool) or status not in {400, 404, 415, 422}:
        return False
    category = stats.get("last_error_category")
    if not isinstance(category, str) and isinstance(diagnostic, Mapping):
        category = diagnostic.get("error_message_category")
    blocked = {
        "authentication_or_permission",
        "permission_denied",
        "capacity_or_quota",
        "quota_or_rate_limit",
        "rate_limited",
        "transport_error",
        "provider_internal_error",
    }
    if category in blocked:
        return False
    # An OpenRouter 404 has many meanings (unknown model, region, etc.).
    # Only a classified require_parameters routing rejection may fall back.
    if status == 404:
        return (
            category == "required_parameters_no_endpoint"
            and stats.get("response_strategy") in {"json_schema", "native_tool_call", "json_object"}
        )
    # Other 4xx must be a rejection of a structured attempt, never ordinary
    # chat, to prevent a free retry after unrelated provider errors.
    mode = stats.get("response_strategy")
    if mode is not None and mode not in {"json_schema", "native_tool_call", "json_object", "unselected"}:
        return False
    return True
