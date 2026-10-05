#!/usr/bin/env python3
"""Semantic-authoring integrity rules shared by writer and publication gates.

This module owns invariants that must hold *before* LaTeX projection.  In
particular, mathematical LaTeX commands may not live in plain authoring text;
they must be explicitly delimited so the semantic migration layer can create
InlineMath/DisplayMath nodes.  The publication layer may repeat these checks as
defense in depth, but it is not responsible for repairing violations.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterator


RAW_MATH_COMMAND_RE = re.compile(
    r"\\(?:"
    r"in|notin|nabla|delta|partial|int|iint|iiint|oint|sum|prod|"
    r"alpha|beta|gamma|sigma|epsilon|varepsilon|omega|theta|lambda|mu|"
    r"phi|psi|rho|tau|Omega|Gamma|Delta|Sigma|Phi|Psi|"
    r"mathbf|mathrm|mathbb|mathcal|frac|sqrt|cdot|times|pm|mp|"
    r"le|ge|neq|approx|equiv|infty|forall|exists|subset|supset"
    r")\b"
)


@dataclass(frozen=True)
class AuthoringIntegrityIssue:
    code: str
    message: str
    offset: int

    def format(self) -> str:
        return f"{self.code} at offset {self.offset}: {self.message}"


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return bool(backslashes % 2)


def _find_unescaped(text: str, token: str, start: int) -> int:
    cursor = start
    while True:
        found = text.find(token, cursor)
        if found < 0:
            return -1
        if not _is_escaped(text, found):
            return found
        cursor = found + len(token)


def _iter_plain_authoring_regions(text: str) -> Iterator[tuple[int, int]]:
    """Yield spans outside explicit authoring math delimiters.

    Supported legacy authoring math delimiters are single-dollar inline math,
    ``\\(...\\)`` and ``\\[...\\]``.  Unmatched delimiters are deliberately
    treated as plain text so malformed authoring remains visible to validators
    rather than being silently swallowed.
    """

    cursor = 0
    plain_start = 0
    length = len(text)

    while cursor < length:
        # LaTeX explicit inline/display math delimiters.
        opener = None
        closer = None
        opener_len = 0
        if text.startswith(r"\(", cursor) and not _is_escaped(text, cursor):
            opener, closer, opener_len = r"\(", r"\)", 2
        elif text.startswith(r"\[", cursor) and not _is_escaped(text, cursor):
            opener, closer, opener_len = r"\[", r"\]", 2
        elif text[cursor] == "$" and not _is_escaped(text, cursor):
            # Keep $$ untouched: the migration contract only recognizes
            # single-dollar inline math and must not guess display semantics.
            if cursor + 1 < length and text[cursor + 1] == "$":
                cursor += 2
                continue
            opener, closer, opener_len = "$", "$", 1

        if opener is None:
            cursor += 1
            continue

        if closer == "$":
            end = cursor + 1
            while end < length:
                if text[end] == "$" and not _is_escaped(text, end):
                    if end + 1 < length and text[end + 1] == "$":
                        end += 2
                        continue
                    break
                end += 1
            if end >= length:
                cursor += opener_len
                continue
            close_end = end + 1
        else:
            end = _find_unescaped(text, closer, cursor + opener_len)
            if end < 0:
                cursor += opener_len
                continue
            close_end = end + len(closer)

        if plain_start < cursor:
            yield plain_start, cursor
        cursor = close_end
        plain_start = close_end

    if plain_start < length:
        yield plain_start, length


def audit_authoring_math_integrity(text: str) -> tuple[AuthoringIntegrityIssue, ...]:
    """Report raw mathematical LaTeX commands outside explicit math regions."""

    value = str(text or "")
    issues: list[AuthoringIntegrityIssue] = []
    for start, end in _iter_plain_authoring_regions(value):
        region = value[start:end]
        for match in RAW_MATH_COMMAND_RE.finditer(region):
            absolute = start + match.start()
            issues.append(
                AuthoringIntegrityIssue(
                    "RAW_MATH_IN_AUTHORING_TEXT",
                    (
                        f"raw mathematical LaTeX command {match.group(0)!r} "
                        "must be enclosed in an explicit math region"
                    ),
                    absolute,
                )
            )
    return tuple(issues)


def assert_authoring_math_integrity(text: str) -> None:
    """Raise ``ValueError`` when authoring text leaks mathematical commands."""

    issues = audit_authoring_math_integrity(text)
    if issues:
        raise ValueError("; ".join(issue.format() for issue in issues))

class AuthoringIntegrityError(ValueError):
    """Raised when section authoring content violates a semantic invariant."""

    def __init__(self, messages: tuple[str, ...]):
        self.messages = tuple(messages)
        super().__init__("; ".join(self.messages))


def audit_section_records_math_integrity(sections) -> tuple[str, ...]:
    """Audit persisted legacy section records before they enter semantic assembly."""

    messages: list[str] = []
    for index, section in enumerate(sections or []):
        if not isinstance(section, dict):
            continue
        content = str(section.get("content", "") or "")
        issues = audit_authoring_math_integrity(content)
        if not issues:
            continue
        identity = str(section.get("section_id") or section.get("title") or index)
        for issue in issues:
            messages.append(f"section {identity}: {issue.format()}")
    return tuple(messages)


def assert_section_records_math_integrity(sections) -> None:
    """Fail before persistence when any section contains raw math commands."""

    messages = audit_section_records_math_integrity(sections)
    if messages:
        raise AuthoringIntegrityError(messages)
