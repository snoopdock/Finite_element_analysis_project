"""Endpoint-scoped, fail-closed response capability negotiation for AE-32C.

Discovery is optional: it makes one bounded, read-only request to a fixed
OpenRouter metadata origin. Metadata is a routing hint, not validation or an
assertion about the model's actual output. No repository content is sent.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import time
from typing import Callable, Mapping, Any
from urllib.parse import quote

import requests

from providers.response_limits import load_bounded_json, close_response

_VALID_MODEL_ID = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.:-]+$")
_OPENROUTER_ORIGIN = "https://openrouter.ai/api/v1"


@dataclass(frozen=True)
class EndpointCapabilities:
    model: str
    endpoint_count: int
    json_schema: bool
    native_tools: bool
    json_object: bool
    source: str

    def select_mode(self) -> str:
        return select_response_mode(json_schema=self.json_schema,
                                    native_tool_calls=self.native_tools,
                                    json_object=self.json_object)


def unknown_capabilities(model: str, source: str = "unknown") -> EndpointCapabilities:
    return EndpointCapabilities(model, 0, False, False, False, source)


def parse_openrouter_endpoints(payload: Any, model: str) -> EndpointCapabilities:
    """Only explicit per-endpoint parameters count; model-wide union is insufficient.

    An endpoint with `structured_outputs` supports strict JSON Schema; plain
    `response_format` alone is used only as JSON-object mode. Endpoint metadata
    is NOT proof of correct schema enforcement, so all results are validated.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        return unknown_capabilities(model, "invalid_metadata")
    data = payload["data"]
    if data.get("id") != model or not isinstance(data.get("endpoints"), list):
        return unknown_capabilities(model, "model_or_endpoints_mismatch")
    endpoints = data["endpoints"]
    if len(endpoints) > 256:
        return unknown_capabilities(model, "metadata_exceeds_endpoint_limit")
    observed: list[set[str]] = []
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            continue
        values = endpoint.get("supported_parameters")
        if not isinstance(values, list) or len(values) > 256 or not all(isinstance(v, str) for v in values):
            continue
        observed.append(set(values))
    return EndpointCapabilities(
        model=model,
        endpoint_count=len(observed),
        json_schema=any("structured_outputs" in params for params in observed),
        native_tools=any("tools" in params for params in observed),
        json_object=any("response_format" in params or "structured_outputs" in params for params in observed),
        source="openrouter_endpoint_metadata" if observed else "no_verified_endpoint_parameters",
    )


class OpenRouterCapabilityCache:
    """Short-lived cache; never cache authorizations or raw metadata bodies."""

    def __init__(self, ttl_seconds: int = 300, clock: Callable[[], float] = time.monotonic):
        if isinstance(ttl_seconds, bool) or not 30 <= ttl_seconds <= 3600:
            raise ValueError("TTL must be between 30 and 3600 seconds")
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self._values: dict[tuple[str, str], tuple[float, EndpointCapabilities]] = {}
        self.http_requests = 0

    def get(self, *, model: str, api_key: str, timeout_seconds: float = 4.0,
            request_get: Callable[..., Any] | None = None) -> EndpointCapabilities:
        # Reject paths that could change the host or add segments/query params.
        if not isinstance(model, str) or not _VALID_MODEL_ID.fullmatch(model):
            return unknown_capabilities(str(model)[:100], "invalid_model_identifier")
        key = (_OPENROUTER_ORIGIN, model)
        now = self.clock()
        cached = self._values.get(key)
        if cached and cached[0] > now:
            return cached[1]
        author, slug = model.split("/", 1)
        url = f"{_OPENROUTER_ORIGIN}/models/{quote(author, safe='')}/{quote(slug, safe='')}/endpoints"
        getter = request_get or requests.get
        response = None
        try:
            self.http_requests += 1
            response = getter(url,
                headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
                timeout=max(1.0, min(6.0, float(timeout_seconds))), stream=True, allow_redirects=False)
            if response.status_code != 200:
                result = unknown_capabilities(model, "metadata_http_failure")
            else:
                payload = load_bounded_json(response, max_bytes=128_000)
                result = parse_openrouter_endpoints(payload, model)
        except (requests.exceptions.RequestException, ValueError, TypeError, OverflowError):
            result = unknown_capabilities(model, "metadata_unavailable")
        finally:
            if response is not None:
                close_response(response)
        self._values[key] = (self.clock() + self.ttl_seconds, result)
        return result


def select_response_mode(*, json_schema: bool, native_tool_calls: bool,
                         json_object: bool) -> str:
    """Pure policy shared by endpoint adapters and deterministic tests."""
    if json_schema:
        return "json_schema"
    if native_tool_calls:
        return "native_tool_call"
    if json_object:
        return "json_object"
    return "plain_text"
