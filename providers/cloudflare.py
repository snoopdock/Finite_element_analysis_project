#!/usr/bin/env python3
"""Cloudflare Workers AI provider implementation."""

import json
import os
import sys
import time

import requests

from providers.base import ProviderToolCall
from processing.response_extractor import (
    LLMResponseExtractor,
    LLMResponseExtractionError,
)

CF_BASE = "https://api.cloudflare.com/client/v4"
DEFAULT_MODEL = "@cf/meta/llama-3.1-8b-instruct-fast"
DEFAULT_MAX_RESPONSE_CHARS = 200_000
MAX_ALLOWED_RESPONSE_CHARS = 2_000_000
QWEN_NATIVE_TOOL_MODEL = "@cf/qwen/qwen3.8-27b"
CLOUDFLARE_JSON_MODE_MODELS = frozenset({
    "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    "@cf/meta/llama-3-8b-instruct",
    "@cf/meta/llama-3.1-8b-instruct",
    "@hf/nousresearch/hermes-2-pro-mistral-7b",
    "@hf/thebloke/deepseek-coder-6.7b-instruct-awq",
    "@cf/deepseek-ai/deepseek-r1-distill-qwen-32b",
})


def _reject_duplicate_tool_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _reject_tool_constant(_value):
    raise ValueError("nonstandard_json_constant")


class CloudflareProvider:
    def __init__(
        self,
        account_id,
        api_token,
        models,
        max_tokens_per_call=2500,
        max_logical_calls=20,
        max_response_chars=None,
    ):
        self.provider_name = "cloudflare"
        self.account_id = account_id
        self.api_token = api_token
        self.models = models if models else [DEFAULT_MODEL]
        self.model_index = 0
        self.call_counts = {model: 0 for model in self.models}
        self.logical_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0
        self.http_attempts = 0
        self.http_status_counts = {}
        self.response_chars_total = 0
        self.response_chars_max = 0
        self.total_calls = 0
        self.max_tokens_per_call = max_tokens_per_call
        self.oversized_responses = 0
        self.response_chars_rejected_total = 0
        if max_response_chars is None:
            raw_response_limit = os.environ.get(
                "FEA_MAX_LLM_RESPONSE_CHARS", str(DEFAULT_MAX_RESPONSE_CHARS)
            )
            try:
                resolved_response_limit = int(raw_response_limit)
            except (TypeError, ValueError):
                resolved_response_limit = DEFAULT_MAX_RESPONSE_CHARS
        else:
            try:
                resolved_response_limit = int(max_response_chars)
            except (TypeError, ValueError) as exc:
                raise ValueError("max_response_chars must be a positive integer") from exc
        if not 1 <= resolved_response_limit <= MAX_ALLOWED_RESPONSE_CHARS:
            raise ValueError(
                f"max_response_chars must be between 1 and {MAX_ALLOWED_RESPONSE_CHARS}"
            )
        self.max_response_chars = resolved_response_limit
        try:
            self.timeout_seconds = max(10, min(600, int(os.environ.get("FEA_LLM_REQUEST_TIMEOUT_SECONDS", "180"))))
        except (TypeError, ValueError):
            self.timeout_seconds = 180
        try:
            self.max_retries = max(1, min(5, int(os.environ.get("FEA_LLM_RETRY_ATTEMPTS", "3"))))
        except (TypeError, ValueError):
            self.max_retries = 3
        self.usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "responses_with_usage": 0,
            "reported_cost_usd": 0.0,
            "responses_with_cost": 0,
        }
        self.structured_json_calls = 0
        self.native_tool_call_requests = 0
        self.native_tool_call_responses = 0
        self.native_tool_call_failures = 0

        env_limit = os.environ.get("FEA_MAX_LLM_CALLS")
        if env_limit:
            try:
                max_logical_calls = int(env_limit)
            except ValueError:
                pass

        self.max_logical_calls = max_logical_calls
        self.extractor = LLMResponseExtractor(verbose=False)

    def get_next_model(self):
        if not self.models:
            return None
        model = self.models[self.model_index]
        self.model_index = (self.model_index + 1) % len(self.models)
        return model

    def budget_exhausted(self) -> bool:
        return (
            self.max_logical_calls is not None
            and self.logical_calls >= self.max_logical_calls
        )

    def chat(self, messages, temperature=0.2, max_tokens=None, model=None, response_format=None, tools=None):
        """Send one logical LLM call; HTTP retries do not count as new calls.

        ``response_format`` is intentionally restricted to the JSON-object mode
        used by AE-32C's structured action protocol. Ordinary baseline calls
        omit it and continue to receive unconstrained text responses.
        """
        if self.budget_exhausted():
            return None, "Local logical-call budget exhausted"

        self.logical_calls += 1
        self.total_calls = self.logical_calls

        if os.environ.get("FEA_BENCHMARK_MODE") == "1" and os.environ.get(
            "FEA_BENCHMARK_FORCE_MAX_TOKENS"
        ) == "1":
            try:
                max_tokens = max(256, min(12000, int(os.environ.get(
                    "FEA_MAX_TOKENS_PER_CALL", self.max_tokens_per_call
                ))))
            except (TypeError, ValueError):
                max_tokens = self.max_tokens_per_call
        elif max_tokens is None:
            max_tokens = self.max_tokens_per_call

        if model is None:
            model = self.get_next_model()
        if not model:
            self.failed_calls += 1
            return None, "No models available"

        url = f"{CF_BASE}/accounts/{self.account_id}/ai/run/{model}"
        headers = {"Authorization": "Bearer " + self.api_token}
        payload = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if response_format is not None:
            if response_format != {"type": "json_object"} or tools is not None:
                self.failed_calls += 1
                return None, "Unsupported structured response format"
            payload["response_format"] = {"type": "json_object"}
            self.structured_json_calls += 1
        if tools is not None:
            if (
                not isinstance(tools, list)
                or len(tools) != 1
                or not isinstance(tools[0], dict)
                or not isinstance(tools[0].get("name"), str)
                or not isinstance(tools[0].get("description"), str)
                or not isinstance(tools[0].get("parameters"), dict)
            ):
                self.failed_calls += 1
                self.native_tool_call_failures += 1
                return None, "Invalid native response-tool definition"
            payload["tools"] = tools
            self.native_tool_call_requests += 1

        for attempt in range(self.max_retries):
            self.http_attempts += 1
            resp = None
            try:
                resp = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout_seconds,
                )

                self.http_status_counts[str(resp.status_code)] = self.http_status_counts.get(str(resp.status_code), 0) + 1
                if resp.status_code == 429:
                    wait = min(120, 30 * (2 ** attempt))
                    print(
                        f"  [Cloudflare] Rate limited, waiting {wait}s...",
                        file=sys.stderr,
                    )
                    if attempt + 1 < self.max_retries:
                        time.sleep(wait)
                        continue
                    self.failed_calls += 1
                    return None, "HTTP 429: rate limit after retries"

                if resp.status_code == 402:
                    self.failed_calls += 1
                    return None, "HTTP 402: Budget exhausted"

                if resp.status_code >= 400:
                    # Never echo provider-controlled HTTP error bodies into logs or
                    # reports: they may contain credentials, request fragments, or
                    # other sensitive diagnostic data. Do not require response.text.
                    self.failed_calls += 1
                    return None, f"HTTP {resp.status_code}: upstream error body omitted"

                data = resp.json()
                usage = data.get("usage") if isinstance(data, dict) else None
                if not isinstance(usage, dict) and isinstance(data, dict):
                    result_block = data.get("result")
                    if isinstance(result_block, dict):
                        usage = result_block.get("usage")
                if isinstance(usage, dict):
                    try:
                        prompt_tokens = max(0, int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0))
                        completion_tokens = max(0, int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0))
                        total_tokens = max(0, int(usage.get("total_tokens", prompt_tokens + completion_tokens) or 0))
                    except (TypeError, ValueError):
                        prompt_tokens = completion_tokens = total_tokens = 0
                    self.usage["prompt_tokens"] += prompt_tokens
                    self.usage["completion_tokens"] += completion_tokens
                    self.usage["total_tokens"] += total_tokens
                    self.usage["responses_with_usage"] += 1

                if tools is not None and isinstance(data, dict):
                    result_block = data.get("result")
                    raw_tool_calls = (
                        result_block.get("tool_calls")
                        if isinstance(result_block, dict)
                        else None
                    )
                    if raw_tool_calls not in (None, []):
                        if not isinstance(raw_tool_calls, list) or len(raw_tool_calls) != 1:
                            self.failed_calls += 1
                            self.native_tool_call_failures += 1
                            return None, "Native response-tool call count invalid"
                        raw_call = raw_tool_calls[0]
                        if not isinstance(raw_call, dict):
                            self.failed_calls += 1
                            self.native_tool_call_failures += 1
                            return None, "Native response-tool envelope invalid"
                        call_name = raw_call.get("name")
                        call_arguments = raw_call.get("arguments")
                        if isinstance(call_arguments, str):
                            try:
                                call_arguments = json.loads(
                                    call_arguments,
                                    object_pairs_hook=_reject_duplicate_tool_keys,
                                    parse_constant=_reject_tool_constant,
                                )
                            except (TypeError, ValueError, json.JSONDecodeError):
                                self.failed_calls += 1
                                self.native_tool_call_failures += 1
                                return None, "Native response-tool arguments invalid"
                        if not isinstance(call_name, str) or not isinstance(call_arguments, dict):
                            self.failed_calls += 1
                            self.native_tool_call_failures += 1
                            return None, "Native response-tool arguments invalid"
                        try:
                            encoded_call = json.dumps(
                                {"name": call_name, "arguments": call_arguments},
                                ensure_ascii=False,
                                separators=(",", ":"),
                                allow_nan=False,
                            )
                        except (TypeError, ValueError):
                            self.failed_calls += 1
                            self.native_tool_call_failures += 1
                            return None, "Native response-tool arguments invalid"
                        if len(encoded_call) > self.max_response_chars:
                            self.failed_calls += 1
                            self.native_tool_call_failures += 1
                            self.oversized_responses += 1
                            self.response_chars_rejected_total += len(encoded_call)
                            return None, (
                                "Decoded response exceeds character limit "
                                f"({len(encoded_call)} > {self.max_response_chars}; "
                                f"max_response_chars={self.max_response_chars})"
                            )
                        self.native_tool_call_responses += 1
                        self.call_counts[model] = self.call_counts.get(model, 0) + 1
                        self.successful_calls += 1
                        self.response_chars_total += len(encoded_call)
                        self.response_chars_max = max(self.response_chars_max, len(encoded_call))
                        return ProviderToolCall(call_name, call_arguments), None

                try:
                    text = self.extractor.extract(
                        data,
                        provider="cloudflare",
                        model=model,
                        raise_on_failure=True,
                    )
                except LLMResponseExtractionError as exc:
                    self.failed_calls += 1
                    return None, f"Extraction failed: {exc.message}"

                if len(text) > self.max_response_chars:
                    self.failed_calls += 1
                    self.oversized_responses += 1
                    self.response_chars_rejected_total += len(text)
                    return None, (
                        "Decoded response exceeds character limit "
                        f"({len(text)} > {self.max_response_chars}; "
                        f"max_response_chars={self.max_response_chars})"
                    )

                self.call_counts[model] = self.call_counts.get(model, 0) + 1
                self.successful_calls += 1
                self.response_chars_total += len(text)
                self.response_chars_max = max(self.response_chars_max, len(text))
                return text, None

            except requests.exceptions.RequestException as exc:
                if attempt + 1 >= self.max_retries:
                    self.failed_calls += 1
                    return None, str(exc)
                time.sleep(10 * (attempt + 1))

            except ValueError as exc:
                self.failed_calls += 1
                return None, f"Invalid JSON response: {exc}"
            finally:
                # Close every obtained HTTP response, including status errors,
                # retry/continue paths, parse failures, oversized payloads and
                # successful returns. A minimal fake/adapter response may not
                # expose close(), so cleanup must remain defensive.
                if resp is not None:
                    close_response = getattr(resp, "close", None)
                    if callable(close_response):
                        try:
                            close_response()
                        except Exception:
                            # Cleanup must not replace the primary provider
                            # result or error with a secondary close failure.
                            pass

        self.failed_calls += 1
        return None, "Max retries exceeded"

    def get_capabilities(self):
        """Declare model-scoped adapter support; live model behavior remains unverified."""
        selected_model = self.models[0] if len(self.models) == 1 else None
        native_tool_model = selected_model == QWEN_NATIVE_TOOL_MODEL
        json_object_model = selected_model in CLOUDFLARE_JSON_MODE_MODELS
        return {
            "json_object_mode": json_object_model,
            "json_schema_mode": False,
            "native_tool_calls": native_tool_model,
            "finish_reason_reporting": False,
        }

    def chat_with_response_tool(
        self,
        messages,
        *,
        tool_definition,
        temperature=0.2,
        max_tokens=None,
        model=None,
    ):
        """Return one native function call as data; never execute the function."""
        selected_model = model or (
            self.models[0] if len(self.models) == 1 else None
        )
        if selected_model != QWEN_NATIVE_TOOL_MODEL:
            return None, "Native response-tool mode is not enabled for this model"
        if not isinstance(tool_definition, dict):
            return None, "Invalid response-tool definition"
        function = tool_definition.get("function")
        if (
            tool_definition.get("type") != "function"
            or not isinstance(function, dict)
            or not isinstance(function.get("name"), str)
            or not isinstance(function.get("description"), str)
            or not isinstance(function.get("parameters"), dict)
        ):
            return None, "Invalid response-tool definition"
        # The /ai/run REST API documents the native {name, description,
        # parameters} tool shape and returns result.tool_calls[]. This avoids
        # introducing a second transport path just for Qwen.
        native_tool = {
            "name": function["name"],
            "description": function["description"],
            "parameters": function["parameters"],
        }
        return self.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=selected_model,
            tools=[native_tool],
        )

    def chat_structured(self, messages, temperature=0.2, max_tokens=None, model=None):
        """Request API-level JSON mode for a structured AE-32C action response."""
        return self.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
            response_format={"type": "json_object"},
        )

    def get_stats(self):
        return {
            "provider": self.provider_name,
            "endpoint": "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}",
            "total_calls": self.logical_calls,
            "logical_calls": self.logical_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "http_attempts": self.http_attempts,
            "http_status_counts": dict(self.http_status_counts),
            "response_chars_total": self.response_chars_total,
            "response_chars_max": self.response_chars_max,
            "max_response_chars": self.max_response_chars,
            "oversized_responses": self.oversized_responses,
            "response_chars_rejected_total": self.response_chars_rejected_total,
            "per_model": dict(self.call_counts),
            "usage": dict(self.usage),
            "max_tokens_per_call": self.max_tokens_per_call,
            "max_logical_calls": self.max_logical_calls,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "structured_json_calls": self.structured_json_calls,
            "native_tool_call_requests": self.native_tool_call_requests,
            "native_tool_call_responses": self.native_tool_call_responses,
            "native_tool_call_failures": self.native_tool_call_failures,
            "extraction_stats": self.extractor.get_stats(),
            "learned_paths": self.extractor.get_learned_paths(),
        }
