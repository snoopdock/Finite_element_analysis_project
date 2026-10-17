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


PROVIDER_ENDPOINTS = {
    "nararouter": "https://router.bynara.id/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
}

DEFAULT_MODELS = {
    "nararouter": "agnes-2.5-flash",
    "openrouter": "deepseek/deepseek-v4.1-flash-1017",
}

TRANSIENT_HTTP_STATUSES = {408, 425, 429, 500, 502, 503, 504}


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

    def _error(self, message: str) -> Tuple[None, str]:
        safe = str(message)[:500]
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
        if self.budget_exhausted():
            return None, "Local logical-call budget exhausted"

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
                )
            except requests.exceptions.RequestException as exc:
                if attempt + 1 < self.max_retries:
                    time.sleep(min(30, 2 ** attempt))
                    continue
                return self._error(f"{self.provider_name} transport error: {type(exc).__name__}")

            self.last_http_status = int(response.status_code)
            status_key = str(response.status_code)
            self.http_status_counts[status_key] = self.http_status_counts.get(status_key, 0) + 1
            if response.status_code in TRANSIENT_HTTP_STATUSES:
                if attempt + 1 < self.max_retries:
                    retry_after = response.headers.get("Retry-After", "")
                    try:
                        wait_seconds = max(0, min(60, int(float(retry_after))))
                    except (TypeError, ValueError):
                        wait_seconds = min(30, 2 ** attempt)
                    time.sleep(wait_seconds)
                    continue
                return self._error(
                    f"{self.provider_name} HTTP {response.status_code} after {self.max_retries} attempts"
                )

            if response.status_code >= 400:
                return self._error(f"{self.provider_name} HTTP {response.status_code}")

            try:
                data = response.json()
            except (ValueError, TypeError):
                if attempt + 1 < self.max_retries:
                    time.sleep(min(10, 2 ** attempt))
                    continue
                return self._error(f"{self.provider_name} returned invalid JSON (HTTP {response.status_code})")

            choices = data.get("choices") if isinstance(data, dict) else None
            if not isinstance(choices, list) or not choices:
                keys = sorted(str(key) for key in data.keys()) if isinstance(data, dict) else []
                return self._error(
                    f"{self.provider_name} malformed chat completion: missing choices (HTTP {response.status_code}; keys={keys[:12]})"
                )
            first = choices[0] if isinstance(choices[0], dict) else {}
            text = _extract_content(first.get("message"))
            if not text:
                # Some OpenAI-compatible services return a refusal or legacy text field.
                text = first.get("text") if isinstance(first.get("text"), str) else None
            if not text or not text.strip():
                finish_reason = first.get("finish_reason", "unknown")
                return self._error(
                    f"{self.provider_name} returned empty content (HTTP {response.status_code}; finish_reason={finish_reason})"
                )

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

        return self._error(f"{self.provider_name} request exhausted retry budget")

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
            "usage": dict(self.usage),
            "per_model": {name: dict(values) for name, values in self.per_model.items()},
            "last_errors": list(self.last_errors),
        }
