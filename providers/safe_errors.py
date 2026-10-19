"""Redaction helpers for provider error messages.

Raw upstream response bodies must not be included in public error messages. This
module is a last-line defense for bounded diagnostics, not a substitute for
omitting response bodies and authorization material at the call site.
"""
from __future__ import annotations

import re

_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b[A-Z0-9_.-]*(?:API[_-]?KEY|ACCESS[_-]?TOKEN|REFRESH[_-]?TOKEN|AUTH[_-]?TOKEN|PASSWORD|CLIENT[_-]?SECRET|SECRET|TOKEN|AUTHORIZATION)\b\s*[:=]\s*)([^\r\n,;]+)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}")
_TOKEN_SHAPES = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})\b"
)


def sanitize_provider_error(message: object, *, limit: int = 500) -> str:
    """Redact common secret patterns before truncating a provider diagnostic."""
    text = str(message)
    text = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}<redacted>", text)
    text = _BEARER.sub("Bearer <redacted>", text)
    text = _TOKEN_SHAPES.sub("<redacted-token>", text)
    if len(text) > limit:
        text = text[:limit] + "…<truncated-after-redaction>"
    return text
