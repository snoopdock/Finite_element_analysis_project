#!/usr/bin/env python3
"""Lossless lexical scanner for structured authoring text.

The scanner identifies mathematical regions while leaving their contents
opaque. Non-math regions remain eligible for the semantic-marker parser.
This module performs no LaTeX validation, semantic resolution, or document
model construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Union


@dataclass(frozen=True)
class TextRegion:
    """A region where semantic-marker syntax is active."""

    source: str
    kind: str = "text"


@dataclass(frozen=True)
class MathRegion:
    """An opaque mathematical authoring region, including its delimiter."""

    source: str
    delimiter: str
    kind: str = "math"


AuthoringRegion = Union[TextRegion, MathRegion]


def scan_authoring_text(text: str) -> List[AuthoringRegion]:
    """Partition authoring text into marker-active text and opaque math.

    Supported mathematical delimiters are ``$...$``, ``$$...$$``, and
    ``\\[...\\]``. Escaped dollars are ordinary text. An unmatched delimiter
    is left as ordinary text rather than consuming the remainder of the input.
    The returned source strings preserve the original input exactly.
    """
    if not isinstance(text, str):
        raise TypeError("Authoring text must be a string.")
    if not text:
        return []

    regions: List[AuthoringRegion] = []
    text_start = 0
    cursor = 0
    length = len(text)

    def flush_text(end: int) -> None:
        nonlocal text_start
        if text_start < end:
            regions.append(TextRegion(text[text_start:end]))

    while cursor < length:
        if text[cursor] == "\\" and cursor + 1 < length and text[cursor + 1] == "$":
            cursor += 2
            continue

        delimiter = None
        if text.startswith("$$", cursor):
            delimiter = "$$"
            close = text.find("$$", cursor + 2)
        elif text.startswith("\\[", cursor):
            delimiter = "\\["
            close = text.find("\\]", cursor + 2)
        elif text[cursor] == "$":
            delimiter = "$"
            close = _find_inline_dollar(text, cursor + 1)
        else:
            cursor += 1
            continue

        if close == -1:
            cursor += len(delimiter)
            continue

        flush_text(cursor)
        end = close + (2 if delimiter in {"$$", "\\["} else 1)
        regions.append(MathRegion(text[cursor:end], delimiter))
        cursor = end
        text_start = cursor

    flush_text(length)
    return regions


def _find_inline_dollar(text: str, start: int) -> int:
    """Find the first unescaped dollar closing an inline math region."""
    cursor = start
    while cursor < len(text):
        if text[cursor] == "\\" and cursor + 1 < len(text) and text[cursor + 1] == "$":
            cursor += 2
            continue
        if text[cursor] == "$":
            return cursor
        cursor += 1
    return -1
