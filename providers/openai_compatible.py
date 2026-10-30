#!/usr/bin/env python3
"""OpenAI-compatible chat-completion adapters for NaraRouter and OpenRouter.

Provider responses are treated as untrusted text. This adapter only handles
transport, response extraction, retry policy, and operational usage telemetry.
"""

from __future__ import annotations

import os
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

# OpenRouter documents response_format support for these exact selected models.
# This is adapter/model-pair support, not a guarantee of model compliance.
OPENROUTER_JSON_OBJECT_MODELS = frozenset({
    "nvidia/nemotron-3.5-super-vl:free",
    "google/gemma-4-31b-it:free",
})

TRANSIENT_HTTP_STATUSES = {408, 425, 429, 500, 502, 503, 504}
DEFAULT_MAX_RESPONSE_CHARS = 100_000


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
        self.structured_json_calls = 0

    def get_capabilities(self) -> Dict[str, bool]:
        """Declare only documented or explicitly operator-enabled JSON mode.

        OpenRouter support is limited to the two model IDs verified in its
        current model documentation. NaraRouter is OpenAI-compatible, but its
        published chat-completions reference does not currently document
        response_format; enable it only with an explicit operator opt-in.
        """
        openrouter_json = (
            self.provider_name == "openrouter"
            and self.model in OPENROUTER_JSON_OBJECT_MODELS
        )
        nararouter_json = (
            self.provider_name == "nararouter"
            and os.environ.get("FEA_NARAROUTER_JSON_OBJECT_MODE", "").strip() == "1"
        )
        return {
            "json_object_mode": bool(openrouter_json or nararouter_json),
            "json_schema_mode": False,
            "native_tool_calls": False,
            "finish_reason_reporting": True,
        }

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
        response_format: Optional[Dict[str, str]] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        self.last_error_code = None
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
        if response_format is not None:
            if response_format != {"type": "json_object"}:
                return self._error(
                    f"{self.provider_name} unsupported structured response format",
                    code="unsupported_response_format",
                )
            payload["response_format"] = {"type": "json_object"}
            self.structured_json_calls += 1
            if self.provider_name == "openrouter":
                # Do not silently route to an endpoint that drops the requested
                # format. OpenRouter documents this provider preference.
                payload["provider"] = {"require_parameters": True}
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
                # Classify a structured upstream API error without persisting or
                # echoing its potentially sensitive body. Transient statuses are
                # handled by the bounded retry branch above.
                has_error_payload = False
                try:
                    error_payload = load_bounded_json(
                        response, max_bytes=min(self.max_response_bytes, 64_000)
                    )
                    has_error_payload = (
                        isinstance(error_payload, dict) and "error" in error_payload
                    )
                except (ValueError, TypeError, requests.exceptions.RequestException):
                    close_response(response)
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

    def chat_structured(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Request JSON-object mode; local AE-32C validation still checks schema."""
        return self.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
            response_format={"type": "json_object"},
        )

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
            "structured_json_calls": self.structured_json_calls,
        }
