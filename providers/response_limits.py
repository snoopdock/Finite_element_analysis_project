"""Bounded JSON response reader shared by LLM provider adapters.

Real ``requests.Response`` objects are consumed incrementally because provider
requests use ``stream=True``. Lightweight mocked responses without
``iter_content`` are supported for deterministic tests; their decoded payload is
serialized and measured before it is accepted.
"""
from __future__ import annotations

import json
from typing import Any


DEFAULT_MAX_RESPONSE_BYTES = 1_000_000


class ProviderResponseTooLarge(ValueError):
    """An upstream response exceeded the configured byte ceiling."""


def close_response(response: object) -> None:
    """Close a response when the response object provides a close method."""
    close = getattr(response, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            # Closing is best-effort and must not leak transport exceptions.
            pass


def load_bounded_json(
    response: object,
    *,
    max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
) -> Any:
    """Read strict UTF-8 JSON while enforcing a response-body byte limit."""
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
        raise ValueError("max_bytes must be a positive integer")

    iterator = getattr(response, "iter_content", None)
    if callable(iterator):
        chunks: list[bytes] = []
        total = 0
        try:
            for chunk in iterator(chunk_size=8192):
                if not chunk:
                    continue
                if not isinstance(chunk, (bytes, bytearray)):
                    raise ValueError("Provider returned a non-byte response chunk")
                total += len(chunk)
                if total > max_bytes:
                    raise ProviderResponseTooLarge("Provider response body exceeded configured byte limit")
                chunks.append(bytes(chunk))
            raw = b"".join(chunks)
            try:
                return json.loads(raw.decode("utf-8-sig"), parse_constant=_reject_constant)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("Provider returned invalid JSON") from exc
        finally:
            close_response(response)

    # Compatibility path for unit-test doubles and non-requests adapters. It
    # bounds accepted decoded payloads, but cannot bound allocation performed
    # inside a third-party .json() method; production requests use iter_content.
    try:
        payload_reader = getattr(response, "json", None)
        if not callable(payload_reader):
            raise ValueError("Provider response has no JSON reader")
        payload = payload_reader()
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except ProviderResponseTooLarge:
        raise
    except (TypeError, UnicodeEncodeError, ValueError) as exc:
        raise ValueError("Provider returned invalid or non-JSON-compatible data") from exc
    finally:
        close_response(response)
    if len(encoded) > max_bytes:
        raise ProviderResponseTooLarge("Provider response body exceeded configured byte limit")
    return payload


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-standard JSON constant rejected: {value}")
