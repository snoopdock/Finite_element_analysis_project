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
    return {
        "schema_version": "provider-capabilities/v1",
        "provider": str(provider_name or getattr(provider, "provider_name", "") or "unknown")[:100],
        "model": str(model_name or getattr(provider, "model", "") or "provider-default-not-reported")[:200],
        "scope": "adapter_declared_not_model_behavior_verified",
        "capabilities": capabilities,
    }
