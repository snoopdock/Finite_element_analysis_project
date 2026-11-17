#!/usr/bin/env python3
"""Cloudflare Workers AI provider implementation."""

import hashlib
import json
import os
import re
import sys
import time

import requests

from providers.base import ProviderResponse, ProviderToolCall
from providers.message_compatibility import (
    MessageCompatibilityError, coalesce_leading_system_messages,
)
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


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class _SSEProtocolError(ValueError):
    """Safe, structured SSE parse failure; never retains the raw payload."""

    def __init__(self, code, *, event_index=0, payload_bytes=0, payload_sha256="", json_error_position=None):
        super().__init__(code)
        self.code = code
        self.event_index = max(0, int(event_index))
        self.payload_bytes = max(0, int(payload_bytes))
        self.payload_sha256 = payload_sha256 if re.fullmatch(r"[a-f0-9]{64}", payload_sha256 or "") else ""
        self.json_error_position = (
            max(0, int(json_error_position))
            if isinstance(json_error_position, int) and not isinstance(json_error_position, bool)
            else None
        )


def _iter_sse_lines(response, *, max_line_bytes: int):
    """Yield UTF-8-decoded lines from bounded raw transport chunks.

    Unlike iter_lines(), this checks the pending line buffer while bytes arrive,
    so a peer cannot force an unbounded unterminated line allocation.
    """
    pending = bytearray()
    skip_lf_after_cr = False
    for chunk in response.iter_content(chunk_size=4096, decode_unicode=False):
        if chunk is None:
            continue
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8", errors="strict")
        if not isinstance(chunk, (bytes, bytearray)):
            raise _SSEProtocolError("invalid_stream_transport_chunk")
        for byte in chunk:
            if skip_lf_after_cr:
                skip_lf_after_cr = False
                if byte == 0x0A:
                    continue
            if byte == 0x0D:
                yield bytes(pending)
                pending.clear()
                skip_lf_after_cr = True
            elif byte == 0x0A:
                yield bytes(pending)
                pending.clear()
            else:
                pending.append(byte)
                if len(pending) > max_line_bytes:
                    digest = hashlib.sha256(pending[:max_line_bytes]).hexdigest()
                    raise _SSEProtocolError(
                        "stream_line_too_large", payload_bytes=len(pending),
                        payload_sha256=digest,
                    )
    if pending:
        # An unterminated final line is yielded, but its event is not dispatched
        # unless a later blank line was received (the SSE EOF rule).
        yield bytes(pending)


def _iter_sse_data_payloads(response, *, max_line_bytes: int, max_event_bytes: int):
    """Yield complete SSE data payloads, honoring blank-line event boundaries.

    Requests' iter_lines is consumed exactly once. It performs line splitting;
    this layer implements the SSE field and event semantics, including multiple
    data fields, comments, BOM removal, and the three standard line endings.
    """
    data_fields = []
    event_bytes = 0
    first_line = True
    iterator = _iter_sse_lines(response, max_line_bytes=max_line_bytes)
    for raw_line in iterator:
        if raw_line is None:
            continue
        if isinstance(raw_line, bytes):
            try:
                line = raw_line.decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                digest = hashlib.sha256(raw_line).hexdigest()
                raise _SSEProtocolError(
                    "invalid_stream_utf8", payload_bytes=len(raw_line), payload_sha256=digest,
                ) from exc
            line_size = len(raw_line)
        else:
            line = str(raw_line)
            try:
                line_size = len(line.encode("utf-8", errors="strict"))
            except UnicodeEncodeError as exc:
                raise _SSEProtocolError("invalid_stream_utf8") from exc
        if first_line:
            first_line = False
            if line.startswith("\ufeff"):
                line = line[1:]
                line_size = len(line.encode("utf-8"))
        if line_size > max_line_bytes:
            digest = hashlib.sha256(line.encode("utf-8", errors="replace")).hexdigest()
            raise _SSEProtocolError(
                "stream_line_too_large", payload_bytes=line_size, payload_sha256=digest,
            )
        if line == "":
            if data_fields:
                payload = "\n".join(data_fields)
                payload_raw = payload.encode("utf-8")
                digest = hashlib.sha256(payload_raw).hexdigest()
                yield payload, len(payload_raw), digest
            data_fields = []
            event_bytes = 0
            continue
        if line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if separator:
            # The SSE algorithm removes exactly one optional leading U+0020.
            if value.startswith(" "):
                value = value[1:]
        else:
            value = ""
        if field == "data":
            value_bytes = len(value.encode("utf-8"))
            event_bytes += value_bytes
            if event_bytes > max_event_bytes:
                digest = hashlib.sha256("\n".join(data_fields + [value]).encode("utf-8")).hexdigest()
                raise _SSEProtocolError(
                    "stream_event_too_large", payload_bytes=event_bytes, payload_sha256=digest,
                )
            data_fields.append(value)
        # event/id/retry and extension fields are intentionally ignored by
        # this one-shot Chat Completions consumer; they do not affect JSON data.

    # Per the SSE processing model, an event without its terminating blank line
    # is not dispatched at EOF. The caller will classify the stream as incomplete.


def _consume_openai_sse(
    response,
    *,
    max_chars: int,
    started_at: float,
    progress_callback=None,
    max_events: int = 20_000,
):
    """Consume standards-framed OpenAI-compatible Chat Completions SSE.

    Event framing is completed before JSON decoding. All output remains local
    until a complete terminal stream has been received and normalized.
    """
    content_parts = []
    reasoning_parts = []
    reasoning_chars = 0
    tool_calls = {}
    finish_reason = None
    usage = None
    event_count = 0
    first_event_seconds = None
    first_output_seconds = None
    output_chars = 0
    tool_call_delta_count = 0
    wire_chars = 0
    saw_done = False
    last_event_metadata = {}
    max_wire_chars = max_chars * 8 + 131_072

    for payload, payload_bytes, payload_sha256 in _iter_sse_data_payloads(
        response, max_line_bytes=max_wire_chars, max_event_bytes=max_wire_chars,
    ):
        wire_chars += payload_bytes
        if wire_chars > max_wire_chars:
            raise _SSEProtocolError(
                "stream_wire_payload_too_large", event_index=event_count + 1,
                payload_bytes=payload_bytes, payload_sha256=payload_sha256,
            )
        if payload == "[DONE]":
            saw_done = True
            if callable(progress_callback):
                progress_callback({
                    "event_count": event_count,
                    "first_event_seconds": first_event_seconds,
                    "first_output_seconds": first_output_seconds,
                    "output_chars": output_chars,
                    "reasoning_content_chars": reasoning_chars,
                    "tool_call_delta_count": tool_call_delta_count,
                    "terminal_sentinel": True,
                    "finish_reason": finish_reason or "",
                })
            break

        try:
            event = json.loads(payload)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise _SSEProtocolError(
                "malformed_stream_event", event_index=event_count + 1,
                payload_bytes=payload_bytes, payload_sha256=payload_sha256,
                json_error_position=getattr(exc, "pos", None),
            ) from exc
        if not isinstance(event, dict):
            raise _SSEProtocolError(
                "invalid_stream_event_shape", event_index=event_count + 1,
                payload_bytes=payload_bytes, payload_sha256=payload_sha256,
            )
        if "error" in event:
            raise _SSEProtocolError(
                "provider_stream_error", event_index=event_count + 1,
                payload_bytes=payload_bytes, payload_sha256=payload_sha256,
            )

        choices = event.get("choices")
        event_usage = event.get("usage")
        if choices is None and isinstance(event_usage, dict):
            choices = []  # OpenAI-compatible usage-only terminal chunk.
        if not isinstance(choices, list):
            raise _SSEProtocolError(
                "invalid_stream_choices_shape", event_index=event_count + 1,
                payload_bytes=payload_bytes, payload_sha256=payload_sha256,
            )
        if not choices and not isinstance(event_usage, dict):
            raise _SSEProtocolError(
                "invalid_stream_event_shape", event_index=event_count + 1,
                payload_bytes=payload_bytes, payload_sha256=payload_sha256,
            )

        event_count += 1
        if event_count > max_events:
            raise _SSEProtocolError(
                "stream_event_count_exceeded", event_index=event_count,
                payload_bytes=payload_bytes, payload_sha256=payload_sha256,
            )
        if first_event_seconds is None:
            first_event_seconds = max(0.0, time.monotonic() - started_at)
        if isinstance(event_usage, dict):
            usage = event_usage

        for choice in choices:
            if not isinstance(choice, dict):
                raise _SSEProtocolError(
                    "invalid_stream_choice_shape", event_index=event_count,
                    payload_bytes=payload_bytes, payload_sha256=payload_sha256,
                )
            choice_index = choice.get("index", 0)
            if isinstance(choice_index, bool) or not isinstance(choice_index, int) or choice_index != 0:
                raise _SSEProtocolError(
                    "unexpected_stream_choice_index", event_index=event_count,
                    payload_bytes=payload_bytes, payload_sha256=payload_sha256,
                )
            delta = choice.get("delta")
            if delta is None:
                delta = choice.get("message", {})
            if not isinstance(delta, dict):
                raise _SSEProtocolError(
                    "invalid_stream_delta_shape", event_index=event_count,
                    payload_bytes=payload_bytes, payload_sha256=payload_sha256,
                )

            reasoning_value = delta.get("reasoning_content", delta.get("reasoning"))
            if reasoning_value is not None and not isinstance(reasoning_value, str):
                raise _SSEProtocolError(
                    "invalid_stream_reasoning_type", event_index=event_count,
                    payload_bytes=payload_bytes, payload_sha256=payload_sha256,
                )
            if isinstance(reasoning_value, str) and reasoning_value:
                reasoning_parts.append(reasoning_value)
                reasoning_chars += len(reasoning_value)

            content = delta.get("content")
            if content is not None:
                if isinstance(content, str):
                    if content and first_output_seconds is None:
                        first_output_seconds = max(0.0, time.monotonic() - started_at)
                    content_parts.append(content)
                    output_chars += len(content)
                elif isinstance(content, list):
                    for part in content:
                        if not isinstance(part, dict):
                            raise _SSEProtocolError(
                                "invalid_stream_content_part", event_index=event_count,
                                payload_bytes=payload_bytes, payload_sha256=payload_sha256,
                            )
                        if "text" in part and not isinstance(part.get("text"), str):
                            raise _SSEProtocolError(
                                "invalid_stream_content_text_type", event_index=event_count,
                                payload_bytes=payload_bytes, payload_sha256=payload_sha256,
                            )
                        value = part.get("text", "")
                        if value:
                            if first_output_seconds is None:
                                first_output_seconds = max(0.0, time.monotonic() - started_at)
                            content_parts.append(value)
                            output_chars += len(value)
                else:
                    raise _SSEProtocolError(
                        "invalid_stream_content_type", event_index=event_count,
                        payload_bytes=payload_bytes, payload_sha256=payload_sha256,
                    )

            raw_calls = delta.get("tool_calls")
            if raw_calls is not None and not isinstance(raw_calls, list):
                raise _SSEProtocolError(
                    "invalid_stream_tool_calls_shape", event_index=event_count,
                    payload_bytes=payload_bytes, payload_sha256=payload_sha256,
                )
            if isinstance(raw_calls, list):
                for raw_call in raw_calls:
                    tool_call_delta_count += 1
                    if not isinstance(raw_call, dict):
                        raise _SSEProtocolError(
                            "invalid_stream_tool_call_shape", event_index=event_count,
                            payload_bytes=payload_bytes, payload_sha256=payload_sha256,
                        )
                    index = raw_call.get("index", 0)
                    if isinstance(index, bool) or not isinstance(index, int) or index != 0:
                        raise _SSEProtocolError(
                            "unexpected_stream_tool_call_index", event_index=event_count,
                            payload_bytes=payload_bytes, payload_sha256=payload_sha256,
                        )
                    target = tool_calls.setdefault(index, {
                        "id": "", "type": "function",
                        "function": {"name": "", "arguments": ""},
                    })
                    call_id = raw_call.get("id")
                    if call_id is not None and not isinstance(call_id, str):
                        raise _SSEProtocolError(
                            "invalid_stream_tool_call_id_type", event_index=event_count,
                            payload_bytes=payload_bytes, payload_sha256=payload_sha256,
                        )
                    if isinstance(call_id, str) and not target["id"]:
                        target["id"] = call_id[:200]
                    function = raw_call.get("function")
                    if function is not None and not isinstance(function, dict):
                        raise _SSEProtocolError(
                            "invalid_stream_tool_function_shape", event_index=event_count,
                            payload_bytes=payload_bytes, payload_sha256=payload_sha256,
                        )
                    if isinstance(function, dict):
                        name = function.get("name")
                        arguments = function.get("arguments")
                        if name is not None and not isinstance(name, str):
                            raise _SSEProtocolError(
                                "invalid_stream_tool_name_type", event_index=event_count,
                                payload_bytes=payload_bytes, payload_sha256=payload_sha256,
                            )
                        if arguments is not None and not isinstance(arguments, str):
                            raise _SSEProtocolError(
                                "invalid_stream_tool_arguments_type", event_index=event_count,
                                payload_bytes=payload_bytes, payload_sha256=payload_sha256,
                            )
                        if isinstance(name, str):
                            target["function"]["name"] = (target["function"]["name"] + name)[:200]
                        if isinstance(arguments, str):
                            target["function"]["arguments"] += arguments
                            output_chars += len(arguments)
                            if arguments and first_output_seconds is None:
                                first_output_seconds = max(0.0, time.monotonic() - started_at)

            reason = choice.get("finish_reason")
            if reason is not None:
                if not isinstance(reason, str) or reason not in {"stop", "length", "tool_calls", "content_filter", "function_call"}:
                    raise _SSEProtocolError(
                        "invalid_stream_finish_reason", event_index=event_count,
                        payload_bytes=payload_bytes, payload_sha256=payload_sha256,
                    )
                if reason:
                    finish_reason = reason

        last_event_metadata = {
            "event_index": event_count,
            "payload_bytes": payload_bytes,
            "payload_sha256": payload_sha256,
        }
        if callable(progress_callback):
            progress_callback({
                "event_count": event_count,
                "first_event_seconds": first_event_seconds,
                "first_output_seconds": first_output_seconds,
                "output_chars": output_chars,
                "reasoning_content_chars": reasoning_chars,
                "tool_call_delta_count": tool_call_delta_count,
                "terminal_sentinel": False,
                "finish_reason": finish_reason or "",
            })
        if output_chars + reasoning_chars > max_chars:
            raise _SSEProtocolError(
                "stream_response_too_large", event_index=event_count,
                payload_bytes=payload_bytes, payload_sha256=payload_sha256,
            )

    if not saw_done and finish_reason is None:
        raise _SSEProtocolError(
            "incomplete_stream", event_index=event_count,
            payload_bytes=last_event_metadata.get("payload_bytes", 0),
            payload_sha256=last_event_metadata.get("payload_sha256", ""),
        )
    reasoning_content = "".join(reasoning_parts)
    if output_chars + len(reasoning_content) > max_chars:
        raise _SSEProtocolError("stream_response_too_large", event_index=event_count)
    if len(tool_calls) > 1:
        raise _SSEProtocolError("multiple_stream_tool_calls", event_index=event_count)

    message = {"role": "assistant", "content": "".join(content_parts)}
    if reasoning_content:
        message["reasoning_content"] = reasoning_content
    if tool_calls:
        message["tool_calls"] = [tool_calls[index] for index in sorted(tool_calls)]
    normalized = {"choices": [{"message": message, "finish_reason": finish_reason}]}
    if usage is not None:
        normalized["usage"] = usage
    return normalized, {
        "event_count": event_count,
        "first_event_seconds": first_event_seconds,
        "first_output_seconds": first_output_seconds,
        "output_chars": output_chars,
        "reasoning_content_chars": len(reasoning_content),
        "tool_call_delta_count": tool_call_delta_count,
        "terminal_sentinel": saw_done,
        "finish_reason": finish_reason or "",
        "reasoning_content_sha256": hashlib.sha256(reasoning_content.encode("utf-8")).hexdigest() if reasoning_content else None,
        "wire_chars": wire_chars,
    }


def _is_read_timeout_exception(exc: BaseException) -> bool:
    """Recognize requests' wrapped urllib3 read timeouts without parsing payloads."""
    pending = [exc]
    seen = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, requests.exceptions.ReadTimeout):
            return True
        if type(current).__name__ == "ReadTimeoutError":
            return True
        cause = getattr(current, "__cause__", None)
        context = getattr(current, "__context__", None)
        if isinstance(cause, BaseException):
            pending.append(cause)
        if isinstance(context, BaseException):
            pending.append(context)
        for item in getattr(current, "args", ()):
            if isinstance(item, BaseException):
                pending.append(item)
    # requests.Response.iter_content wraps urllib3 ReadTimeoutError in a
    # requests.ConnectionError; classify that wrapper as a read timeout.
    return (
        isinstance(exc, requests.exceptions.ConnectionError)
        and "read timed out" in str(exc).lower()
    )


def _safe_cloudflare_error_diagnostics(response):
    """Extract only bounded, non-sensitive Cloudflare error metadata."""
    status = getattr(response, "status_code", None)
    headers = getattr(response, "headers", {}) or {}
    request_id = ""
    try:
        candidate = headers.get("cf-ray") or headers.get("CF-Ray") or headers.get("cf-request-id") or ""
        if isinstance(candidate, str) and re.fullmatch(r"[A-Za-z0-9-]{8,80}", candidate):
            request_id = candidate
    except Exception:
        request_id = ""

    codes = []
    category = "provider_request_rejected"
    try:
        body = response.json()
    except Exception:
        body = None

    errors = body.get("errors") if isinstance(body, dict) else None
    error_items = list(errors[:5]) if isinstance(errors, list) else []
    openai_error = body.get("error") if isinstance(body, dict) else None
    if isinstance(openai_error, dict):
        error_items.append(openai_error)
    for item in error_items[:6]:
        if not isinstance(item, dict):
            continue
        code = item.get("code")
        if isinstance(code, str) and re.fullmatch(r"[0-9]{1,7}", code):
            code = int(code)
        if isinstance(code, int) and not isinstance(code, bool) and 0 <= code <= 9_999_999:
            codes.append(code)
        message = item.get("message")
        error_type = item.get("type")
        diagnostic_text = " ".join(
            value for value in (message, error_type) if isinstance(value, str)
        ).lower()[:1000]
        if "system message must be at the beginning" in diagnostic_text:
            category = "message_role_sequence_rejected"
        elif any(term in diagnostic_text for term in ("tool", "function", "schema", "parameter", "json", "invalid_request")):
            category = "request_schema_rejected"
        elif any(term in diagnostic_text for term in ("permission", "unauthorized", "forbidden")):
            category = "permission_denied"
        elif any(term in diagnostic_text for term in ("model not found", "unknown model", "model unavailable")):
            category = "model_unavailable"
        elif any(term in diagnostic_text for term in ("quota", "capacity", "rate limit", "budget")):
            category = "capacity_or_quota"

    return {
        "http_status": status if isinstance(status, int) else None,
        "error_category": category,
        "error_codes": sorted(set(codes))[:5],
        "request_id": request_id,
    }


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
            self.timeout_seconds = max(10, min(600, int(os.environ.get("FEA_LLM_REQUEST_TIMEOUT_SECONDS", "90"))))
        except (TypeError, ValueError):
            self.timeout_seconds = 90
        try:
            self.connect_timeout_seconds = max(2, min(60, int(os.environ.get("FEA_LLM_CONNECT_TIMEOUT_SECONDS", "10"))))
        except (TypeError, ValueError):
            self.connect_timeout_seconds = 10
        try:
            self.max_retries = max(1, min(5, int(os.environ.get("FEA_LLM_RETRY_ATTEMPTS", "1"))))
        except (TypeError, ValueError):
            self.max_retries = 1
        self.streaming_enabled = _env_flag("FEA_LLM_STREAMING", False)
        self.stream_fallback_enabled = _env_flag("FEA_LLM_STREAM_FALLBACK", True)
        self.stream_fallback_allow_reasoning_only = _env_flag(
            "FEA_LLM_STREAM_FALLBACK_ALLOW_REASONING_ONLY", False
        )
        try:
            configured_stream_fallbacks = int(os.environ.get("FEA_LLM_STREAM_FALLBACK_MAX_ATTEMPTS", "1"))
        except (TypeError, ValueError):
            configured_stream_fallbacks = 1
        # One process-wide fallback is the hard default/maximum. This bounds
        # extra inference cost even when several logical calls encounter bad streams.
        self.max_stream_fallbacks = max(0, min(1, configured_stream_fallbacks))
        self.stream_fallbacks_used = 0
        requested_effort = os.environ.get("FEA_LLM_REASONING_EFFORT", "").strip().lower()
        self.reasoning_effort = requested_effort if requested_effort in {"low", "medium", "high", "xhigh"} else None
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
        self.last_http_status = None
        self.last_error_category = ""
        self.last_error_codes = []
        self.last_request_id = ""
        self.last_endpoint_mode = ""
        self.last_finish_reason = ""
        self.last_system_messages_coalesced = 0
        self.last_message_compatibility = "not_applied"
        self.last_request_elapsed_seconds = None
        self.last_request_time_to_first_event_seconds = None
        self.last_request_time_to_first_output_seconds = None
        self.last_request_attempt_count = 0
        self.last_request_stream_event_count = 0
        self.last_request_output_chars = 0
        self.last_request_partial_output_chars = 0
        self.last_request_stream_reasoning_chars = 0
        self.last_request_stream_tool_call_delta_count = 0
        self.last_request_stream_terminal_sentinel = False
        self.last_request_stream_finish_reason = ""
        self.last_request_stream_error_code = ""
        self.last_request_stream_error_event_index = 0
        self.last_request_stream_error_payload_bytes = 0
        self.last_request_stream_error_payload_sha256 = ""
        self.last_request_stream_json_error_position = None
        self.last_request_stream_content_type = ""
        self.last_request_stream_content_encoding = ""
        self.last_request_stream_transfer_encoding = ""
        self.last_request_stream_request_id = ""
        self.last_request_stream_fallback_attempted = False
        self.last_request_stream_fallback_succeeded = False
        self.last_request_stream_fallback_reason = ""
        self.last_request_streaming = False
        self.last_request_reasoning_effort = None
        self.last_request_reasoning_content_chars = 0
        self.last_request_reasoning_content_sha256 = None
        self.last_request_max_completion_tokens = None
        self.last_request_error_type = ""

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

    def _record_stream_progress(self, metrics):
        if not isinstance(metrics, dict):
            return
        self.last_request_stream_event_count = int(metrics.get("event_count", 0) or 0)
        first = metrics.get("first_event_seconds")
        if isinstance(first, (int, float)) and not isinstance(first, bool):
            self.last_request_time_to_first_event_seconds = round(max(0.0, float(first)), 3)
        first_output = metrics.get("first_output_seconds")
        if isinstance(first_output, (int, float)) and not isinstance(first_output, bool):
            self.last_request_time_to_first_output_seconds = round(max(0.0, float(first_output)), 3)
        chars = metrics.get("output_chars")
        if isinstance(chars, int) and not isinstance(chars, bool) and chars >= 0:
            self.last_request_partial_output_chars = chars
        reasoning_chars = metrics.get("reasoning_content_chars")
        if isinstance(reasoning_chars, int) and not isinstance(reasoning_chars, bool) and reasoning_chars >= 0:
            self.last_request_stream_reasoning_chars = reasoning_chars
        tool_deltas = metrics.get("tool_call_delta_count")
        if isinstance(tool_deltas, int) and not isinstance(tool_deltas, bool) and tool_deltas >= 0:
            self.last_request_stream_tool_call_delta_count = tool_deltas
        self.last_request_stream_terminal_sentinel = metrics.get("terminal_sentinel") is True
        finish_reason = metrics.get("finish_reason")
        if isinstance(finish_reason, str):
            self.last_request_stream_finish_reason = finish_reason[:80]
        event_metadata = metrics.get("last_event_metadata")
        if isinstance(event_metadata, dict):
            self.last_request_stream_error_event_index = max(0, int(event_metadata.get("event_index", 0) or 0))
            self.last_request_stream_error_payload_bytes = max(0, int(event_metadata.get("payload_bytes", 0) or 0))
            digest = event_metadata.get("payload_sha256")
            if isinstance(digest, str) and re.fullmatch(r"[a-f0-9]{64}", digest):
                self.last_request_stream_error_payload_sha256 = digest

    def chat(
        self,
        messages,
        temperature=0.2,
        max_tokens=None,
        model=None,
        response_format=None,
        tools=None,
        tool_choice=None,
        _openai_compatible=False,
    ):
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

        headers = {
            "Authorization": "Bearer " + self.api_token,
            "Content-Type": "application/json",
        }
        self.last_http_status = None
        self.last_error_category = ""
        self.last_error_codes = []
        self.last_request_id = ""
        self.last_finish_reason = ""
        self.last_system_messages_coalesced = 0
        self.last_message_compatibility = "not_applied"
        if model == QWEN_NATIVE_TOOL_MODEL:
            # Qwen 3.8's chat template accepts only the first system role.
            # AE-32C adds an initial response instruction for native/text
            # output, and the preflight adds an initial probe instruction.
            # Preserve their ordered contents in a single system envelope.
            # Do not silently hoist a later system instruction into higher
            # priority context or modify the original caller's messages.
            try:
                messages, self.last_system_messages_coalesced = (
                    coalesce_leading_system_messages(messages)
                )
                self.last_message_compatibility = "qwen_single_initial_system"
            except MessageCompatibilityError as exc:
                self.last_message_compatibility = "rejected"
                self.last_error_category = "message_role_sequence_rejected"
                self.failed_calls += 1
                return None, f"Invalid Qwen message sequence: {exc}"
        if _openai_compatible:
            # Qwen's model page documents the OpenAI-compatible Chat Completions
            # contract for max_completion_tokens, tools, tool_choice and
            # parallel_tool_calls. Do not send these fields to /ai/run.
            url = (
                f"{CF_BASE}/accounts/{self.account_id}/ai/v1/chat/completions"
            )
            self.last_endpoint_mode = "workers_ai_openai_compatible_chat_completions"
            stream_this_request = self.streaming_enabled
            payload = {
                "model": model,
                "messages": messages,
                "max_completion_tokens": max_tokens,
                "temperature": temperature,
                "stream": stream_this_request,
            }
            if model == QWEN_NATIVE_TOOL_MODEL:
                # Qwen3.8 documents preserved thinking as the default. Send the
                # documented setting explicitly so multi-turn tool history does
                # not accidentally opt out when request defaults change.
                payload["chat_template_kwargs"] = {"preserve_thinking": True}
                if self.reasoning_effort:
                    payload["reasoning_effort"] = self.reasoning_effort
        else:
            url = f"{CF_BASE}/accounts/{self.account_id}/ai/run/{model}"
            self.last_endpoint_mode = "workers_ai_run_chat"
            payload = {
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        if not _openai_compatible:
            stream_this_request = False
        if stream_this_request:
            headers["Accept"] = "text/event-stream"
        request_started = time.monotonic()
        self.last_request_elapsed_seconds = None
        self.last_request_time_to_first_event_seconds = None
        self.last_request_time_to_first_output_seconds = None
        self.last_request_attempt_count = 0
        self.last_request_stream_event_count = 0
        self.last_request_output_chars = 0
        self.last_request_partial_output_chars = 0
        self.last_request_stream_reasoning_chars = 0
        self.last_request_stream_tool_call_delta_count = 0
        self.last_request_stream_terminal_sentinel = False
        self.last_request_stream_finish_reason = ""
        self.last_request_stream_error_code = ""
        self.last_request_stream_error_event_index = 0
        self.last_request_stream_error_payload_bytes = 0
        self.last_request_stream_error_payload_sha256 = ""
        self.last_request_stream_json_error_position = None
        self.last_request_stream_content_type = ""
        self.last_request_stream_content_encoding = ""
        self.last_request_stream_transfer_encoding = ""
        self.last_request_stream_request_id = ""
        self.last_request_stream_fallback_attempted = False
        self.last_request_stream_fallback_succeeded = False
        self.last_request_stream_fallback_reason = ""
        self.last_request_streaming = bool(stream_this_request)
        self.last_request_reasoning_content_chars = 0
        self.last_request_reasoning_content_sha256 = None
        self.last_request_reasoning_effort = (
            self.reasoning_effort if model == QWEN_NATIVE_TOOL_MODEL else None
        )
        self.last_request_max_completion_tokens = max_tokens if isinstance(max_tokens, int) else None
        self.last_request_error_type = ""
        if response_format is not None:
            if (
                _openai_compatible
                or response_format != {"type": "json_object"}
                or tools is not None
            ):
                self.failed_calls += 1
                return None, "Unsupported structured response format"
            payload["response_format"] = {"type": "json_object"}
            self.structured_json_calls += 1
        if tools is not None:
            if (
                not isinstance(tools, list)
                or len(tools) != 1
                or not isinstance(tools[0], dict)
                or tools[0].get("type") != "function"
                or not isinstance(tools[0].get("function"), dict)
                or not isinstance(tools[0]["function"].get("name"), str)
                or not isinstance(tools[0]["function"].get("description"), str)
                or not isinstance(tools[0]["function"].get("parameters"), dict)
            ):
                self.failed_calls += 1
                self.native_tool_call_failures += 1
                return None, "Invalid native response-tool definition"
            # Qwen 3.8 defaults to thinking mode. Its published guidance
            # restricts thinking-mode tool selection to "auto" or "none";
            # forcing a named function is only supported with thinking disabled.
            # Keep thinking enabled and expose exactly one virtual response
            # function, so "auto" cannot select any other function.
            if tool_choice not in (None, "auto"):
                self.failed_calls += 1
                self.native_tool_call_failures += 1
                return None, "Qwen native response tools require auto tool choice"
            if not _openai_compatible:
                self.failed_calls += 1
                self.native_tool_call_failures += 1
                return None, "Native response tools require the OpenAI-compatible Chat Completions endpoint"
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
            payload["parallel_tool_calls"] = False
            self.native_tool_call_requests += 1
            self.last_endpoint_mode = (
                "workers_ai_openai_compatible_chat_completions_auto_tool_choice"
            )

        for attempt in range(self.max_retries):
            self.http_attempts += 1
            resp = None
            try:
                self.last_request_attempt_count = attempt + 1
                resp = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=(self.connect_timeout_seconds, self.timeout_seconds),
                    stream=bool(stream_this_request),
                )

                self.last_http_status = int(resp.status_code)
                self.http_status_counts[str(resp.status_code)] = self.http_status_counts.get(str(resp.status_code), 0) + 1
                if resp.status_code == 429:
                    self.last_error_category = "rate_limited"
                    wait = min(120, 30 * (2 ** attempt))
                    print(
                        f"  [Cloudflare] Rate limited, waiting {wait}s...",
                        file=sys.stderr,
                    )
                    if attempt + 1 < self.max_retries:
                        time.sleep(wait)
                        continue
                    self.failed_calls += 1
                    if tools is not None:
                        self.native_tool_call_failures += 1
                    return None, "HTTP 429: rate limit after retries"

                if resp.status_code == 402:
                    self.last_error_category = "budget_exhausted"
                    self.failed_calls += 1
                    if tools is not None:
                        self.native_tool_call_failures += 1
                    return None, "HTTP 402: budget_exhausted"

                if resp.status_code >= 400:
                    # Do not expose provider-controlled messages. Retain only a
                    # bounded category, numeric error codes and validated request ID.
                    diagnostics = _safe_cloudflare_error_diagnostics(resp)
                    self.last_error_category = diagnostics["error_category"]
                    self.last_error_codes = diagnostics["error_codes"]
                    self.last_request_id = diagnostics["request_id"]
                    self.failed_calls += 1
                    if tools is not None:
                        self.native_tool_call_failures += 1
                    code_text = (
                        "; cloudflare_codes=" + ",".join(str(code) for code in self.last_error_codes)
                        if self.last_error_codes else ""
                    )
                    request_text = (
                        "; request_id=" + self.last_request_id
                        if self.last_request_id else ""
                    )
                    if tools is None:
                        return None, f"HTTP {resp.status_code}: upstream error body omitted"
                    return None, (
                        f"HTTP {resp.status_code}: upstream error body omitted"
                        f"; category={self.last_error_category}"
                        f"{code_text}{request_text}"
                    )

                if stream_this_request:
                    response_headers = getattr(resp, "headers", {}) or {}
                    raw_content_type = response_headers.get("Content-Type", "")
                    self.last_request_stream_content_type = str(raw_content_type).split(";", 1)[0].strip().lower()[:100]
                    self.last_request_stream_content_encoding = str(response_headers.get("Content-Encoding", "")).strip().lower()[:40]
                    self.last_request_stream_transfer_encoding = str(response_headers.get("Transfer-Encoding", "")).strip().lower()[:40]
                    if self.last_request_stream_content_type and self.last_request_stream_content_type != "text/event-stream":
                        raise _SSEProtocolError("unexpected_stream_content_type")
                    candidate_request_id = response_headers.get("cf-ray") or response_headers.get("CF-Ray") or ""
                    if isinstance(candidate_request_id, str) and re.fullmatch(r"[A-Za-z0-9-]{8,80}", candidate_request_id):
                        self.last_request_stream_request_id = candidate_request_id
                    try:
                        data, stream_metrics = _consume_openai_sse(
                            resp,
                            max_chars=self.max_response_chars,
                            started_at=request_started,
                            progress_callback=self._record_stream_progress,
                        )
                    except ValueError as stream_exc:
                        stream_code = str(stream_exc)[:100]
                        self.last_request_stream_error_code = stream_code
                        if isinstance(stream_exc, _SSEProtocolError):
                            self.last_request_stream_error_event_index = stream_exc.event_index
                            self.last_request_stream_error_payload_bytes = stream_exc.payload_bytes
                            self.last_request_stream_error_payload_sha256 = stream_exc.payload_sha256
                            self.last_request_stream_json_error_position = stream_exc.json_error_position
                        no_content_or_tool_action = (
                            self.last_request_partial_output_chars == 0
                            and self.last_request_stream_tool_call_delta_count == 0
                        )
                        no_meaningful_output = (
                            no_content_or_tool_action
                            and (
                                self.last_request_stream_reasoning_chars == 0
                                or self.stream_fallback_allow_reasoning_only
                            )
                        )
                        fallback_eligible_codes = {
                            "incomplete_stream", "malformed_stream_event",
                            "invalid_stream_utf8", "invalid_stream_event_shape",
                            "invalid_stream_choices_shape", "invalid_stream_choice_shape",
                            "invalid_stream_delta_shape", "invalid_stream_reasoning_type",
                            "invalid_stream_content_part", "invalid_stream_content_text_type",
                            "invalid_stream_content_type", "invalid_stream_tool_calls_shape",
                            "invalid_stream_tool_call_shape", "invalid_stream_tool_call_id_type",
                            "invalid_stream_tool_function_shape", "invalid_stream_tool_name_type",
                            "invalid_stream_tool_arguments_type", "invalid_stream_finish_reason",
                            "provider_stream_error", "unexpected_stream_content_type",
                        }
                        fallback_available = (
                            self.stream_fallback_enabled
                            and self.stream_fallbacks_used < self.max_stream_fallbacks
                        )
                        if not (
                            stream_code in fallback_eligible_codes
                            and no_meaningful_output
                            and fallback_available
                        ):
                            raise
                        self.last_request_stream_fallback_attempted = True
                        self.last_request_stream_fallback_reason = stream_code
                        self.stream_fallbacks_used += 1
                        close_failed_stream = getattr(resp, "close", None)
                        if callable(close_failed_stream):
                            try:
                                close_failed_stream()
                            except Exception:
                                pass
                        fallback_payload = dict(payload)
                        fallback_payload["stream"] = False
                        fallback_headers = dict(headers)
                        fallback_headers.pop("Accept", None)
                        self.http_attempts += 1
                        self.last_request_attempt_count += 1
                        try:
                            resp = requests.post(
                                url,
                                headers=fallback_headers,
                                json=fallback_payload,
                                timeout=(self.connect_timeout_seconds, self.timeout_seconds),
                                stream=False,
                            )
                            self.last_http_status = int(resp.status_code)
                            self.http_status_counts[str(resp.status_code)] = (
                                self.http_status_counts.get(str(resp.status_code), 0) + 1
                            )
                            if resp.status_code >= 400:
                                self.last_request_stream_fallback_reason = (
                                    stream_code + ":fallback_http_" + str(resp.status_code)
                                )
                                self.last_error_category = "stream_fallback_rejected"
                                self.last_request_error_type = "FallbackHTTPError"
                                self.failed_calls += 1
                                if tools is not None:
                                    self.native_tool_call_failures += 1
                                return None, (
                                    "Non-streaming recovery request rejected "
                                    f"(HTTP {resp.status_code})"
                                )
                            data = resp.json()
                            self.last_request_stream_fallback_succeeded = True
                            self.last_request_error_type = ""
                            self.last_error_category = ""
                        except requests.exceptions.RequestException as fallback_exc:
                            self.last_error_category = "stream_fallback_transport_error"
                            self.last_request_error_type = type(fallback_exc).__name__[:80]
                            self.last_request_stream_fallback_reason = (
                                stream_code + ":fallback_transport_error"
                            )
                            self.failed_calls += 1
                            if tools is not None:
                                self.native_tool_call_failures += 1
                            return None, "Non-streaming recovery request failed"
                        except (TypeError, ValueError, json.JSONDecodeError):
                            self.last_error_category = "stream_fallback_invalid_response"
                            self.last_request_error_type = "FallbackResponseError"
                            self.last_request_stream_fallback_reason = (
                                stream_code + ":fallback_invalid_response"
                            )
                            self.failed_calls += 1
                            if tools is not None:
                                self.native_tool_call_failures += 1
                            return None, "Non-streaming recovery response was invalid"
                    else:
                        self.last_request_time_to_first_event_seconds = stream_metrics["first_event_seconds"]
                        self.last_request_time_to_first_output_seconds = stream_metrics["first_output_seconds"]
                        self.last_request_stream_event_count = stream_metrics["event_count"]
                        self.last_request_output_chars = stream_metrics["output_chars"]
                        self.last_request_partial_output_chars = stream_metrics["output_chars"]
                        self.last_request_stream_reasoning_chars = stream_metrics["reasoning_content_chars"]
                        self.last_request_stream_tool_call_delta_count = stream_metrics["tool_call_delta_count"]
                        self.last_request_stream_terminal_sentinel = stream_metrics["terminal_sentinel"]
                        self.last_request_stream_finish_reason = stream_metrics["finish_reason"]
                else:
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

                choices_for_finish = data.get("choices") if isinstance(data, dict) else None
                assistant_message = None
                if isinstance(choices_for_finish, list) and choices_for_finish:
                    first_finish_choice = choices_for_finish[0]
                    finish_reason = (
                        first_finish_choice.get("finish_reason")
                        if isinstance(first_finish_choice, dict) else None
                    )
                    self.last_finish_reason = finish_reason[:80] if isinstance(finish_reason, str) else ""
                    assistant_message = (
                        first_finish_choice.get("message")
                        if isinstance(first_finish_choice, dict) else None
                    )
                reasoning_content = None
                if isinstance(assistant_message, dict):
                    reasoning_content = assistant_message.get("reasoning_content")
                    if not isinstance(reasoning_content, str):
                        reasoning_content = assistant_message.get("reasoning")
                if not isinstance(reasoning_content, str) and isinstance(data, dict):
                    result_for_reasoning = data.get("result")
                    if isinstance(result_for_reasoning, dict):
                        reasoning_content = result_for_reasoning.get("reasoning_content")
                        if not isinstance(reasoning_content, str):
                            reasoning_content = result_for_reasoning.get("reasoning")
                if not isinstance(reasoning_content, str):
                    reasoning_content = None
                if reasoning_content:
                    self.last_request_reasoning_content_chars = len(reasoning_content)
                    self.last_request_reasoning_content_sha256 = hashlib.sha256(
                        reasoning_content.encode("utf-8")
                    ).hexdigest()
                    if len(reasoning_content) > self.max_response_chars:
                        self.failed_calls += 1
                        if tools is not None:
                            self.native_tool_call_failures += 1
                        self.oversized_responses += 1
                        self.response_chars_rejected_total += len(reasoning_content)
                        return None, "Reasoning content exceeds configured response character limit"

                if tools is not None and isinstance(data, dict):
                    result_block = data.get("result")
                    raw_tool_calls = (
                        result_block.get("tool_calls")
                        if isinstance(result_block, dict)
                        else data.get("tool_calls")
                    )
                    choices = data.get("choices")
                    if raw_tool_calls in (None, []) and isinstance(choices, list) and choices:
                        first_choice = choices[0]
                        message = first_choice.get("message") if isinstance(first_choice, dict) else None
                        if isinstance(message, dict):
                            raw_tool_calls = message.get("tool_calls")
                            finish_reason = first_choice.get("finish_reason")
                            self.last_finish_reason = (
                                finish_reason[:80] if isinstance(finish_reason, str) else ""
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
                        function_block = raw_call.get("function")
                        if isinstance(function_block, dict):
                            call_name = function_block.get("name")
                            call_arguments = function_block.get("arguments")
                        else:
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
                                if self.last_finish_reason == "length":
                                    # Preserve the truncated argument string as inert data.
                                    # The AE-32C normalizer will reject it and trigger the
                                    # bounded session downgrade; this adapter never executes it.
                                    return ProviderToolCall(
                                        call_name, call_arguments, reasoning_content=reasoning_content
                                    ), None
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
                        if len(encoded_call) + len(reasoning_content or "") > self.max_response_chars:
                            self.failed_calls += 1
                            self.native_tool_call_failures += 1
                            self.oversized_responses += 1
                            self.response_chars_rejected_total += len(encoded_call) + len(reasoning_content or "")
                            return None, "Decoded response exceeds character limit"
                        self.native_tool_call_responses += 1
                        self.last_request_output_chars = len(encoded_call)
                        self.call_counts[model] = self.call_counts.get(model, 0) + 1
                        self.successful_calls += 1
                        self.response_chars_total += len(encoded_call)
                        self.response_chars_max = max(self.response_chars_max, len(encoded_call))
                        return ProviderToolCall(
                            call_name, call_arguments, reasoning_content=reasoning_content
                        ), None
                    if tools is not None:
                        self.native_tool_call_failures += 1
                        message_content = (
                            assistant_message.get("content")
                            if isinstance(assistant_message, dict) else None
                        )
                        if reasoning_content and (
                            message_content is None
                            or (isinstance(message_content, str) and not message_content.strip())
                        ):
                            self.failed_calls += 1
                            self.last_error_category = "empty_reasoning_only_response"
                            self.last_request_error_type = "EmptyModelResponse"
                            return None, "Provider returned reasoning without a usable response action"

                try:
                    text = self.extractor.extract(
                        data,
                        provider="cloudflare",
                        model=model,
                        raise_on_failure=True,
                    )
                except LLMResponseExtractionError as exc:
                    self.failed_calls += 1
                    if tools is not None:
                        self.native_tool_call_failures += 1
                    if reasoning_content and isinstance(assistant_message, dict) and not assistant_message.get("content"):
                        self.last_error_category = "empty_reasoning_only_response"
                        self.last_request_error_type = "EmptyModelResponse"
                        return None, "Provider returned reasoning without a usable response"
                    return None, f"Extraction failed: {exc.message}"

                if not text.strip():
                    self.failed_calls += 1
                    self.last_error_category = (
                        "empty_reasoning_only_response" if reasoning_content
                        else "empty_provider_response"
                    )
                    self.last_request_error_type = "EmptyModelResponse"
                    if tools is not None:
                        self.native_tool_call_failures += 1
                    return None, (
                        "Provider returned reasoning without a usable response"
                        if reasoning_content else "Provider returned an empty response"
                    )

                if len(text) > self.max_response_chars:
                    self.failed_calls += 1
                    self.oversized_responses += 1
                    self.response_chars_rejected_total += len(text)
                    return None, (
                        "Decoded response exceeds character limit "
                        f"({len(text)} > {self.max_response_chars}; "
                        f"max_response_chars={self.max_response_chars})"
                    )

                self.last_request_output_chars = len(text)
                if len(text) + len(reasoning_content or "") > self.max_response_chars:
                    self.failed_calls += 1
                    self.oversized_responses += 1
                    self.response_chars_rejected_total += len(text) + len(reasoning_content or "")
                    if tools is not None:
                        self.native_tool_call_failures += 1
                    return None, "Decoded response exceeds character limit"
                self.call_counts[model] = self.call_counts.get(model, 0) + 1
                self.successful_calls += 1
                self.response_chars_total += len(text)
                self.response_chars_max = max(self.response_chars_max, len(text))
                if tools is not None and reasoning_content:
                    return ProviderResponse(text=text, reasoning_content=reasoning_content), None
                return text, None

            except requests.exceptions.RequestException as exc:
                # A read timeout is ambiguous: the provider may have completed
                # generation after the client stopped waiting. requests wraps
                # urllib3's streaming ReadTimeoutError as ConnectionError, so
                # inspect the exception chain and never replay an ambiguous POST.
                if _is_read_timeout_exception(exc):
                    self.failed_calls += 1
                    if tools is not None:
                        self.native_tool_call_failures += 1
                    self.last_error_category = "read_timeout"
                    self.last_request_error_type = "ReadTimeout"
                    return None, (
                        f"Read timeout after {self.timeout_seconds}s; "
                        f"partial_stream_chars={self.last_request_partial_output_chars}"
                    )
                # Once an SSE response exists, a broken body may follow provider
                # execution. Do not replay it automatically and risk duplicate
                # inference/cost or duplicate model actions.
                if stream_this_request and resp is not None:
                    self.failed_calls += 1
                    if tools is not None:
                        self.native_tool_call_failures += 1
                    self.last_error_category = "stream_interrupted"
                    self.last_request_error_type = type(exc).__name__[:80]
                    return None, "Provider response stream was interrupted"
                if attempt + 1 >= self.max_retries:
                    self.failed_calls += 1
                    if tools is not None:
                        self.native_tool_call_failures += 1
                    self.last_error_category = (
                        "connect_timeout"
                        if isinstance(exc, requests.exceptions.ConnectTimeout)
                        else "transport_error"
                    )
                    self.last_request_error_type = type(exc).__name__[:80]
                    return None, str(exc)
                time.sleep(10 * (attempt + 1))

            except ValueError as exc:
                self.failed_calls += 1
                if tools is not None:
                    self.native_tool_call_failures += 1
                message = str(exc)
                stream_codes = {
                    "malformed_stream_event", "invalid_stream_event_shape",
                    "provider_stream_error", "invalid_stream_tool_call_shape",
                    "invalid_stream_tool_call_index", "unexpected_stream_choice_index",
                    "unexpected_stream_tool_call_index", "multiple_stream_tool_calls",
                    "incomplete_stream", "invalid_stream_finish_reason", "stream_response_too_large",
                    "stream_event_too_large", "stream_wire_payload_too_large",
                    "stream_event_count_exceeded",
                }
                is_stream_error = isinstance(exc, _SSEProtocolError) or message in stream_codes
                self.last_request_stream_error_code = message[:100] if is_stream_error else ""
                if isinstance(exc, _SSEProtocolError):
                    self.last_request_stream_error_event_index = exc.event_index
                    self.last_request_stream_error_payload_bytes = exc.payload_bytes
                    self.last_request_stream_error_payload_sha256 = exc.payload_sha256
                    self.last_request_stream_json_error_position = exc.json_error_position
                self.last_error_category = "invalid_stream" if is_stream_error else "invalid_provider_json"
                self.last_request_error_type = "StreamProtocolError" if is_stream_error else "ValueError"
                return None, (
                    "Invalid or incomplete provider stream"
                    if is_stream_error else "Invalid JSON response"
                )
            finally:
                self.last_request_elapsed_seconds = round(
                    max(0.0, time.monotonic() - request_started), 3
                )
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
        """Return one named native function call as data; never execute it."""
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

        # Qwen 3.8 defaults to thinking mode. Its published tool-selection
        # guidance permits "auto"/"none" while thinking is enabled, but not a
        # forced named-function choice. Supply exactly one virtual response
        # function and use "auto"; the investigator still validates every
        # returned action before any evidence tool can be dispatched.
        return self.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=selected_model,
            tools=[tool_definition],
            tool_choice="auto",
            _openai_compatible=True,
        )

    def chat_openai_compatible(
        self, messages, temperature=0.2, max_tokens=None, model=None
    ):
        """Call the documented OpenAI-compatible Chat Completions endpoint."""
        return self.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
            _openai_compatible=True,
        )

    def chat_text(self, messages, temperature=0.2, max_tokens=None, model=None):
        """Request unconstrained text through the OpenAI-compatible chat endpoint.

        This is the provider adapter's universal fallback path when a selected
        model or account rejects structured response parameters.
        """
        return self.chat_openai_compatible(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
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
            "native_tool_endpoint": "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1/chat/completions",
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
            "stream_fallback_enabled": self.stream_fallback_enabled,
            "stream_fallbacks_used": self.stream_fallbacks_used,
            "stream_fallbacks_max": self.max_stream_fallbacks,
            "structured_json_calls": self.structured_json_calls,
            "native_tool_call_requests": self.native_tool_call_requests,
            "native_tool_call_responses": self.native_tool_call_responses,
            "native_tool_call_failures": self.native_tool_call_failures,
            "last_http_status": self.last_http_status,
            "last_error_category": self.last_error_category,
            "last_error_codes": list(self.last_error_codes),
            "last_request_id": self.last_request_id,
            "last_endpoint_mode": self.last_endpoint_mode,
            "last_finish_reason": self.last_finish_reason,
            "last_reasoning_content_chars": self.last_request_reasoning_content_chars,
            "last_reasoning_content_sha256": self.last_request_reasoning_content_sha256,
            "last_system_messages_coalesced": self.last_system_messages_coalesced,
            "last_message_compatibility": self.last_message_compatibility,
            "extraction_stats": self.extractor.get_stats(),
            "learned_paths": self.extractor.get_learned_paths(),
            "request_diagnostics": {
                "elapsed_seconds": self.last_request_elapsed_seconds,
                "time_to_first_event_seconds": self.last_request_time_to_first_event_seconds,
                "time_to_first_output_seconds": self.last_request_time_to_first_output_seconds,
                "attempt_count": self.last_request_attempt_count,
                "stream_event_count": self.last_request_stream_event_count,
                "output_chars": self.last_request_output_chars,
                "partial_output_chars": self.last_request_partial_output_chars,
                "stream_reasoning_chars": self.last_request_stream_reasoning_chars,
                "stream_tool_call_delta_count": self.last_request_stream_tool_call_delta_count,
                "terminal_sentinel_observed": self.last_request_stream_terminal_sentinel,
                "stream_finish_reason": self.last_request_stream_finish_reason,
                "stream_error_code": self.last_request_stream_error_code,
                "stream_error_event_index": self.last_request_stream_error_event_index,
                "stream_error_payload_bytes": self.last_request_stream_error_payload_bytes,
                "stream_error_payload_sha256": self.last_request_stream_error_payload_sha256,
                "stream_json_error_position": self.last_request_stream_json_error_position,
                "stream_content_type": self.last_request_stream_content_type,
                "stream_content_encoding": self.last_request_stream_content_encoding,
                "stream_transfer_encoding": self.last_request_stream_transfer_encoding,
                "stream_request_id": self.last_request_stream_request_id,
                "stream_fallback_enabled": self.stream_fallback_enabled,
                "stream_fallback_allow_reasoning_only": self.stream_fallback_allow_reasoning_only,
                "stream_fallback_attempted": self.last_request_stream_fallback_attempted,
                "stream_fallback_succeeded": self.last_request_stream_fallback_succeeded,
                "stream_fallback_reason": self.last_request_stream_fallback_reason,
                "stream_fallbacks_used": self.stream_fallbacks_used,
                "stream_fallbacks_max": self.max_stream_fallbacks,
                "streaming": self.last_request_streaming,
                "connect_timeout_seconds": self.connect_timeout_seconds,
                "read_timeout_seconds": self.timeout_seconds,
                "reasoning_effort": self.last_request_reasoning_effort,
                "reasoning_content_chars": self.last_request_reasoning_content_chars,
                "reasoning_content_sha256": self.last_request_reasoning_content_sha256,
                "max_completion_tokens": self.last_request_max_completion_tokens,
                "finish_reason": self.last_finish_reason,
                "error_type": self.last_request_error_type,
                "error_category": self.last_error_category or "none",
            },
        }
