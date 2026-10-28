#!/usr/bin/env python3
"""OpenAI-compatible chat-completion adapters for NaraRouter and OpenRouter.

Provider responses are treated as untrusted text. This adapter only handles
transport, response extraction, retry policy, and operational usage telemetry.
"""

from __future__ import annotations

import os
import re
import time
from typing import Dict, List, Optional, Tuple

import requests

from providers.safe_errors import sanitize_provider_error
from providers.response_limits import (
    DEFAULT_MAX_RESPONSE_BYTES,
    ProviderResponseTooLarge,
    close_response,
    load_bounded_json,
)


PROVIDER_ENDPOINTS = {
    "nararouter": "https://router.bynara.id/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
}

DEFAULT_MODELS = {
    "nararouter": "agnes-2.5-flash",
    "openrouter": "deepseek/deepseek-v4.1-flash-1017",
}

TRANSIENT_HTTP_STATUSES = {408, 425, 429, 500, 502, 503, 504}
DEFAULT_MAX_RESPONSE_CHARS = 100_000
_SAFE_ERROR_TOKEN = re.compile(r"^[A-Za-z0-9_.:/\-\[\]]{1,100}$")
_SAFE_ERROR_FIELD_NAMES = {"type", "code", "param", "message", "details", "metadata", "status", "request_id", "trace_id"}


def _classify_error_message(message: object) -> str | None:
    """Classify an upstream error message without retaining its free-form text.

    The message is treated as untrusted. Only a small category is emitted; raw
    content, URLs, tokens, and provider-specific prose are never persisted.
    """
    if not isinstance(message, str) or not message.strip():
        return None
    text = re.sub(r"\s+", " ", message).strip().lower()[:4000]

    model_rejected = (
        re.search(r"\b(model|deployment)\b.{0,100}\b(not found|unknown|invalid|unavailable|unsupported|does not exist|not available|not recognized)\b", text)
        or re.search(r"\b(not found|unknown|invalid|unavailable|unsupported|does not exist|not available|not recognized)\b.{0,100}\b(model|deployment)\b", text)
    )
    if model_rejected:
        return "model_identifier_rejected"

    if re.search(r"\b(unauthorized|invalid api key|authentication failed|permission denied|forbidden|not authorized|access denied|invalid token)\b", text):
        return "authentication_or_permission"

    if re.search(r"\b(rate limit|quota|billing|insufficient (credit|balance|funds)|too many requests)\b", text):
        return "quota_or_rate_limit"

    if (
        re.search(r"\b(unsupported|unknown|invalid|unrecognized|unexpected|not allowed)\s+(request\s+)?(parameter|param|field|argument)\b", text)
        or re.search(r"\b(parameter|param|field|argument)\b.{0,80}\b(unsupported|unknown|invalid|unrecognized|unexpected|not allowed|not supported)\b", text)
        or re.search(r"\b(extra inputs are not permitted|unknown field|unexpected field)\b", text)
    ):
        return "request_parameter_rejected"

    if re.search(r"\b(endpoint|route|url path|http method)\b.{0,80}\b(not found|unsupported|not allowed|invalid)\b", text):
        return "endpoint_or_method_rejected"

    if (
        re.search(r"\b(invalid json|malformed json|invalid request body|request body|schema validation|invalid type|required field|missing field|expected (an? )?(object|array|string|number|integer|boolean)|messages\b.{0,80}\b(required|invalid|must)\b|must be (an? )?(object|array|string|number|integer|boolean))", text)
    ):
        return "request_schema_or_body_rejected"

    if re.search(r"\b(internal server error|server error|upstream error|temporarily unavailable|service unavailable)\b", text):
        return "provider_internal_error"

    return "other_unclassified"


def http_error_diagnostic(payload: object, status_code: int, *, body_status: str = "json") -> dict[str, object]:
    """Expose safe structure from an HTTP error without persisting its message/body.

    Only allowlisted field names and conservative identifier-like values are
    retained. Free-form messages, request IDs, arbitrary keys, headers, and raw
    response text are intentionally excluded.
    """
    result: dict[str, object] = {"http_status": int(status_code), "body_status": body_status}
    if not isinstance(payload, dict):
        result["body_shape"] = "non_object"
        return result
    result["body_shape"] = "object"
    result["top_level_error_fields"] = sorted(
        key for key in payload if isinstance(key, str) and key in _SAFE_ERROR_FIELD_NAMES
    )
    error = payload.get("error")
    if isinstance(error, dict):
        result["error_shape"] = "object"
        result["error_fields"] = sorted(
            key for key in error if isinstance(key, str) and key in _SAFE_ERROR_FIELD_NAMES
        )
        for source_key, target_key in (("type", "error_type"), ("code", "error_code"), ("param", "error_param")):
            value = error.get(source_key)
            if isinstance(value, str) and value:
                result[target_key] = value if _SAFE_ERROR_TOKEN.fullmatch(value) else "present_unclassified"

        # Keep only a coarse category derived from the free-form message; never
        # persist the message itself. This makes generic HTTP 400s actionable
        # without exposing arbitrary upstream prose in evaluation artifacts.
        message_category = _classify_error_message(error.get("message"))
        if message_category:
            result["error_message_category"] = message_category

        # Correlation IDs are useful for provider-side support. Emit only a
        # short identifier-shaped value, never arbitrary text.
        request_id = error.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            request_id = payload.get("request_id", payload.get("trace_id"))
        if isinstance(request_id, str) and len(request_id) <= 100 and re.fullmatch(r"[A-Za-z0-9_.:/-]{1,100}", request_id):
            result["error_request_id"] = request_id
    elif isinstance(error, str):
        result["error_shape"] = "string"
        result["error_fields"] = []
    elif error is None:
        result["error_shape"] = "absent"
        result["error_fields"] = []
    else:
        result["error_shape"] = "other"
        result["error_fields"] = []
    return result


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _extract_content(message: object) -> Optional[str]:
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces = []
        for part in content:
            if isinstance(part, str):
                pieces.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                pieces.append(part["text"])
        joined = "".join(pieces)
        return joined if joined.strip() else None
    return None


def completion_envelope_diagnostic(payload: object) -> dict[str, object]:
    """Return only whitelisted structural observations, never upstream content.

    A 200 response can be an upstream error object or a nonstandard wrapper.
    Neither is a successful chat completion; the adapter stays fail-closed.
    """
    if not isinstance(payload, dict):
        return {"envelope_kind": "non_object", "choices_shape": "absent", "has_error_object": False}
    choices = payload.get("choices")
    shape = "nonempty_list" if isinstance(choices, list) and choices else (
        "empty_list" if isinstance(choices, list) else
        "absent" if "choices" not in payload else "wrong_type")
    # No arbitrary keys, error strings, content snippets, model names, or IDs.
    kind = "standard_choices" if shape == "nonempty_list" else (
        "upstream_error_object" if isinstance(payload.get("error"), (dict, str)) else
        "alternate_wrapper" if isinstance(payload.get("data"), dict) or isinstance(payload.get("result"), dict) else
        "unrecognized_object")
    return {"envelope_kind": kind, "choices_shape": shape,
            "has_error_object": isinstance(payload.get("error"), (dict, str))}


class OpenAICompatibleProvider:
    """Small retry-bounded adapter for NaraRouter/OpenRouter chat completions."""

    def __init__(
        self,
        provider_name: str,
        api_key: str,
        model: str,
        max_tokens_per_call: int = 2500,
        max_logical_calls: int = 20,
        timeout_seconds: Optional[int] = None,
        max_retries: Optional[int] = None,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        max_response_chars: int = DEFAULT_MAX_RESPONSE_CHARS,
    ):
        name = str(provider_name or "").strip().lower()
        if name not in PROVIDER_ENDPOINTS:
            raise ValueError(f"Unsupported OpenAI-compatible provider: {name!r}")
        if not str(api_key or "").strip():
            raise ValueError(f"API key is required for provider {name}")
        if not str(model or "").strip():
            raise ValueError(f"A model ID is required for provider {name}")

        self.provider_name = name
        self.api_key = str(api_key).strip()
        self.model = str(model).strip()
        self.endpoint = PROVIDER_ENDPOINTS[name]
        self.max_tokens_per_call = int(max_tokens_per_call)
        self.max_logical_calls = int(max_logical_calls) if max_logical_calls is not None else None
        self.timeout_seconds = int(timeout_seconds or _int_env(
            "FEA_LLM_REQUEST_TIMEOUT_SECONDS", 300, 10, 600
        ))
        self.max_retries = int(max_retries or _int_env(
            "FEA_LLM_RETRY_ATTEMPTS", 3, 1, 5
        ))
        if isinstance(max_response_bytes, bool) or not isinstance(max_response_bytes, int) or not 1 <= max_response_bytes <= 8_000_000:
            raise ValueError("max_response_bytes must be between 1 and 8000000")
        if isinstance(max_response_chars, bool) or not isinstance(max_response_chars, int) or not 1 <= max_response_chars <= 1_000_000:
            raise ValueError("max_response_chars must be between 1 and 1000000")
        self.max_response_bytes = max_response_bytes
        self.max_response_chars = max_response_chars

        self.logical_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0
        self.http_attempts = 0
        self.http_status_counts: Dict[str, int] = {}
        self.finish_reason_counts: Dict[str, int] = {}
        self.last_http_status: Optional[int] = None
        self.last_returned_model: Optional[str] = None
        self.response_chars_total = 0
        self.response_chars_max = 0
        self.usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "responses_with_usage": 0,
            "reported_cost_usd": 0.0,
            "responses_with_cost": 0,
        }
        self.per_model: Dict[str, Dict[str, int]] = {}
        self.last_errors: List[str] = []
        self.last_error_code: Optional[str] = None
        self.error_counts: Dict[str, int] = {}
        self.envelope_diagnostic_counts: Dict[str, int] = {}
        self.last_envelope_diagnostic: dict[str, object] | None = None
        self.last_http_error_diagnostic: dict[str, object] | None = None
        self.http_error_diagnostic_counts: Dict[str, int] = {}

    @property
    def total_calls(self) -> int:
        """Backward-compatible alias for the provider's logical-call count."""
        return self.logical_calls

    def budget_exhausted(self) -> bool:
        return (
            self.max_logical_calls is not None
            and self.logical_calls >= self.max_logical_calls
        )

    def _effective_max_tokens(self, requested: Optional[int]) -> int:
        if os.environ.get("FEA_BENCHMARK_MODE") == "1" and os.environ.get(
            "FEA_BENCHMARK_FORCE_MAX_TOKENS"
        ) == "1":
            return _int_env("FEA_MAX_TOKENS_PER_CALL", self.max_tokens_per_call, 256, 12000)
        if requested is None:
            return self.max_tokens_per_call
        return max(1, min(12000, int(requested)))

    def _record_usage(self, payload: object, model: str) -> None:
        if not isinstance(payload, dict):
            return
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            return
        prompt = usage.get("prompt_tokens", usage.get("input_tokens", 0))
        completion = usage.get("completion_tokens", usage.get("output_tokens", 0))
        total = usage.get("total_tokens")
        try:
            prompt = max(0, int(prompt or 0))
            completion = max(0, int(completion or 0))
            total = max(0, int(total if total is not None else prompt + completion))
        except (TypeError, ValueError):
            return
        self.usage["prompt_tokens"] += prompt
        self.usage["completion_tokens"] += completion
        self.usage["total_tokens"] += total
        self.usage["responses_with_usage"] += 1
        raw_cost = usage.get("cost", payload.get("cost"))
        if raw_cost is not None:
            try:
                self.usage["reported_cost_usd"] += max(0.0, float(raw_cost))
                self.usage["responses_with_cost"] += 1
            except (TypeError, ValueError):
                pass
        per_model = self.per_model.setdefault(model, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
        per_model["calls"] += 1
        per_model["prompt_tokens"] += prompt
        per_model["completion_tokens"] += completion
        per_model["total_tokens"] += total

    def _error(self, message: str, *, code: str = "provider_error") -> Tuple[None, str]:
        safe = sanitize_provider_error(message)
        safe_code = str(code)[:80] if isinstance(code, str) and code else "provider_error"
        self.last_error_code = safe_code
        self.error_counts[safe_code] = self.error_counts.get(safe_code, 0) + 1
        self.last_errors.append(safe)
        self.last_errors = self.last_errors[-20:]
        self.failed_calls += 1
        return None, safe

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        self.last_error_code = None
        self.last_http_error_diagnostic = None
        if self.budget_exhausted():
            return self._error("Local logical-call budget exhausted", code="logical_call_budget_exhausted")

        self.logical_calls += 1
        selected_model = str(model or self.model).strip()
        token_cap = self._effective_max_tokens(max_tokens)
        payload = {
            "model": selected_model,
            "messages": messages,
            "temperature": float(temperature),
            "max_tokens": token_cap,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.provider_name == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/snoopdock/Finite_element_analysis_project"
            headers["X-Title"] = "Finite Element Analysis Pipeline"

        for attempt in range(self.max_retries):
            self.http_attempts += 1
            try:
                response = requests.post(
                    self.endpoint,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout_seconds,
                    stream=True,
                )
            except requests.exceptions.RequestException as exc:
                if attempt + 1 < self.max_retries:
                    time.sleep(min(30, 2 ** attempt))
                    continue
                return self._error(f"{self.provider_name} transport error: {type(exc).__name__}", code="transport_error")

            self.last_http_status = int(response.status_code)
            status_key = str(response.status_code)
            self.http_status_counts[status_key] = self.http_status_counts.get(status_key, 0) + 1
            if response.status_code in TRANSIENT_HTTP_STATUSES:
                close_response(response)
                if attempt + 1 < self.max_retries:
                    retry_after = response.headers.get("Retry-After", "")
                    try:
                        wait_seconds = max(0, min(60, int(float(retry_after))))
                    except (TypeError, ValueError):
                        wait_seconds = min(30, 2 ** attempt)
                    time.sleep(wait_seconds)
                    continue
                return self._error(
                    f"{self.provider_name} HTTP {response.status_code} after {self.max_retries} attempts",
                    code="transient_http_status_exhausted",
                )

            if response.status_code >= 400:
                # Retain only allowlisted structural error metadata. The free-form
                # upstream message/body is never copied into logs or artifacts.
                error_payload: object = None
                body_status = "json"
                try:
                    error_payload = load_bounded_json(
                        response, max_bytes=min(self.max_response_bytes, 64_000)
                    )
                except ProviderResponseTooLarge:
                    body_status = "too_large"
                    close_response(response)
                except (ValueError, TypeError, requests.exceptions.RequestException):
                    body_status = "unreadable_or_non_json"
                    close_response(response)
                has_error_payload = isinstance(error_payload, dict) and "error" in error_payload
                diagnostic = http_error_diagnostic(error_payload, response.status_code, body_status=body_status)
                self.last_http_error_diagnostic = diagnostic
                diagnostic_key = str(diagnostic.get("error_code") or diagnostic.get("error_type") or diagnostic.get("error_shape") or body_status)
                self.http_error_diagnostic_counts[diagnostic_key] = self.http_error_diagnostic_counts.get(diagnostic_key, 0) + 1
                error_code = "provider_api_error_payload" if has_error_payload else "http_error"
                return self._error(
                    f"{self.provider_name} HTTP {response.status_code}",
                    code=error_code,
                )

            try:
                data = load_bounded_json(response, max_bytes=self.max_response_bytes)
            except ProviderResponseTooLarge:
                return self._error(f"{self.provider_name} response exceeded configured size limit", code="response_too_large")
            except requests.exceptions.RequestException as exc:
                return self._error(f"{self.provider_name} response stream error: {type(exc).__name__}", code="response_stream_error")
            except (ValueError, TypeError):
                if attempt + 1 < self.max_retries:
                    time.sleep(min(10, 2 ** attempt))
                    continue
                return self._error(f"{self.provider_name} returned invalid JSON (HTTP {response.status_code})", code="invalid_json_response")

            diagnostic = completion_envelope_diagnostic(data)
            # The summary is deliberately non-sensitive and carries no raw
            # upstream JSON or error text into persisted evaluation evidence.
            self.last_envelope_diagnostic = diagnostic
            kind = str(diagnostic["envelope_kind"])
            self.envelope_diagnostic_counts[kind] = self.envelope_diagnostic_counts.get(kind, 0) + 1
            choices = data.get("choices") if isinstance(data, dict) else None
            if not isinstance(choices, list) or not choices:
                return self._error(
                    f"{self.provider_name} malformed chat completion: missing choices (HTTP {response.status_code})",
                    code="malformed_completion_envelope",
                )
            first = choices[0] if isinstance(choices[0], dict) else {}
            finish_reason = str(first.get("finish_reason", "unknown"))
            # A cut-off or filtered completion must not be passed to the
            # strict JSON parser as an ordinary full response. Record only a
            # bounded category; never persist the partial text or error body.
            if finish_reason in {"length", "max_tokens"}:
                self.finish_reason_counts[finish_reason] = self.finish_reason_counts.get(finish_reason, 0) + 1
                return self._error(f"{self.provider_name} completion truncated at model token limit", code="completion_truncated")
            if finish_reason in {"content_filter", "safety"}:
                self.finish_reason_counts[finish_reason] = self.finish_reason_counts.get(finish_reason, 0) + 1
                return self._error(f"{self.provider_name} completion filtered by provider", code="completion_filtered")
            text = _extract_content(first.get("message"))
            if not text:
                # Some OpenAI-compatible services return a refusal or legacy text field.
                text = first.get("text") if isinstance(first.get("text"), str) else None
            if not text or not text.strip():
                finish_reason = first.get("finish_reason", "unknown")
                return self._error(
                    f"{self.provider_name} returned empty content (HTTP {response.status_code}; finish_reason={finish_reason})",
                    code="empty_completion_content",
                )

            if len(text) > self.max_response_chars:
                return self._error(f"{self.provider_name} response text exceeded configured character limit", code="response_text_too_large")

            self._record_usage(data, selected_model)
            self.successful_calls += 1
            self.last_returned_model = str(data.get("model", selected_model)) if isinstance(data, dict) else selected_model
            finish_reason = str(first.get("finish_reason", "unknown"))
            self.finish_reason_counts[finish_reason] = self.finish_reason_counts.get(finish_reason, 0) + 1
            self.response_chars_total += len(text)
            self.response_chars_max = max(self.response_chars_max, len(text))
            per_model = self.per_model.setdefault(selected_model, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
            if not isinstance(data.get("usage"), dict):
                per_model["calls"] += 1
            return text, None

        return self._error(f"{self.provider_name} request exhausted retry budget", code="retry_budget_exhausted")

    def get_stats(self) -> Dict:
        return {
            "provider": self.provider_name,
            "model": self.model,
            "endpoint": self.endpoint,
            "total_calls": self.logical_calls,
            "logical_calls": self.logical_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "http_attempts": self.http_attempts,
            "http_status_counts": dict(self.http_status_counts),
            "last_http_status": self.last_http_status,
            "last_returned_model": self.last_returned_model,
            "finish_reason_counts": dict(self.finish_reason_counts),
            "response_chars_total": self.response_chars_total,
            "response_chars_max": self.response_chars_max,
            "max_logical_calls": self.max_logical_calls,
            "max_tokens_per_call": self.max_tokens_per_call,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "max_response_bytes": self.max_response_bytes,
            "max_response_chars": self.max_response_chars,
            "usage": dict(self.usage),
            "per_model": {name: dict(values) for name, values in self.per_model.items()},
            "last_errors": list(self.last_errors),
            "last_error_code": self.last_error_code,
            "error_counts": dict(self.error_counts),
            "last_envelope_diagnostic": dict(self.last_envelope_diagnostic) if self.last_envelope_diagnostic else None,
            "envelope_diagnostic_counts": dict(self.envelope_diagnostic_counts),
            "last_http_error_diagnostic": dict(self.last_http_error_diagnostic) if self.last_http_error_diagnostic else None,
            "http_error_diagnostic_counts": dict(self.http_error_diagnostic_counts),
        }
