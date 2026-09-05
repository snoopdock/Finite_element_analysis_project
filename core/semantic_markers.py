#!/usr/bin/env python3
"""Parser for the small semantic-reference protocol used by the writer.

The parser performs syntax recognition only. It does not resolve identifiers,
create semantic objects, or render LaTeX.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import List, Union


SUPPORTED_MARKERS = {"EQ", "CITE", "REF", "NEW_EQ"}
_MARKER_RE = re.compile(
    r"\[\[(?P<kind>[A-Za-z][A-Za-z0-9_]*):(?P<identifier>[^\[\]\s]+)\]\]"
)
_ANY_MARKER_RE = re.compile(r"\[\[(?P<body>[^\[\]]*)\]\]")


class SemanticMarkerError(ValueError):
    """Raised when writer output violates the marker syntax contract."""


@dataclass(frozen=True)
class TextSegment:
    """Unmarked free-form authorial text."""

    text: str

    kind: str = "text"


@dataclass(frozen=True)
class SemanticMarker:
    """One syntactically valid semantic reference marker."""

    marker_type: str
    identifier: str

    kind: str = "marker"


AuthoringSegment = Union[TextSegment, SemanticMarker]


def parse_authoring_text(text: str) -> List[AuthoringSegment]:
    """Parse writer output into ordered text and semantic-reference segments.

    Unmarked prose is preserved verbatim. All double-bracket markers are
    treated as protocol syntax; unknown or malformed markers are rejected.
    """
    if not isinstance(text, str):
        raise SemanticMarkerError("Authoring output must be a string.")

    if not text:
        return []

    segments: List[AuthoringSegment] = []
    cursor = 0

    for match in _MARKER_RE.finditer(text):
        prefix = text[cursor:match.start()]
        if prefix:
            segments.append(TextSegment(prefix))

        marker_type = match.group("kind")
        identifier = match.group("identifier")

        if marker_type not in SUPPORTED_MARKERS:
            raise SemanticMarkerError(
                f"Unknown semantic marker type: {marker_type}."
            )

        if not identifier.strip():
            raise SemanticMarkerError(
                f"Empty identifier for marker type: {marker_type}."
            )

        segments.append(
            SemanticMarker(
                marker_type=marker_type,
                identifier=identifier,
            )
        )
        cursor = match.end()

    suffix = text[cursor:]
    if suffix:
        segments.append(TextSegment(suffix))

    _reject_unparsed_markers(text, segments)
    return _coalesce_text_segments(segments)


def _reject_unparsed_markers(text: str, parsed: List[AuthoringSegment]) -> None:
    """Reject any bracketed marker-like syntax not consumed by the parser."""
    recognized_spans = []
    cursor = 0
    for segment in parsed:
        if isinstance(segment, TextSegment):
            cursor += len(segment.text)
        else:
            marker_text = f"[[{segment.marker_type}:{segment.identifier}]]"
            start = text.find(marker_text, cursor)
            if start == -1:
                raise SemanticMarkerError(
                    f"Internal marker parsing inconsistency for {marker_text!r}."
                )
            recognized_spans.append((start, start + len(marker_text)))
            cursor = start + len(marker_text)

    for match in _ANY_MARKER_RE.finditer(text):
        span = (match.start(), match.end())
        if any(span == known for known in recognized_spans):
            continue
        body = match.group("body")
        marker_type = body.split(":", 1)[0] if ":" in body else body
        raise SemanticMarkerError(
            f"Unknown or malformed semantic marker: {marker_type!r}."
        )

    if "[[" in text and not _ANY_MARKER_RE.search(text):
        raise SemanticMarkerError("Unterminated semantic marker detected.")


def _coalesce_text_segments(
    segments: List[AuthoringSegment],
) -> List[AuthoringSegment]:
    """Merge adjacent prose segments while preserving marker order."""
    result: List[AuthoringSegment] = []
    for segment in segments:
        if (
            result
            and isinstance(result[-1], TextSegment)
            and isinstance(segment, TextSegment)
        ):
            result[-1] = TextSegment(result[-1].text + segment.text)
        else:
            result.append(segment)
    return result
