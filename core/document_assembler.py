#!/usr/bin/env python3
"""Deterministic conversion from writer markers to document-model objects."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Set
import uuid

from core.document_model import (
    CitationOccurrence,
    CitationClusterOccurrence,
    CrossReferenceOccurrence,
    DisplayMath,
    EquationOccurrence,
    EquationProposalReference,
    InlineMath,
    Paragraph,
    Section,
    Text,
    DocumentModelError,
)
from core.semantic_markers import SemanticMarker, TextSegment, parse_authoring_text
from core.authoring_integrity import audit_authoring_math_integrity


_OCCURRENCE_NAMESPACE = uuid.UUID("8e5e8d8d-84f0-4d1d-8d3f-2ce2d6ad6b25")


def _iter_legacy_math(text: str):
    """Yield ordered legacy prose/math fragments without interpreting meaning.

    Only unescaped single-dollar delimiters are recognized.  Malformed or
    unmatched dollar signs remain ordinary text.  This parser is used solely
    by the explicit migration path; the semantic marker protocol itself does
    not require LaTeX delimiters.
    """
    cursor = 0
    length = len(text)
    while cursor < length:
        start = cursor
        while start < length:
            if text[start] == "$" and (start == 0 or text[start - 1] != "\\"):
                # ``$$`` belongs to a different legacy syntax and is left
                # untouched rather than guessed here.
                if start + 1 < length and text[start + 1] == "$":
                    start += 2
                    continue
                break
            start += 1

        if start >= length:
            yield ("text", text[cursor:], cursor, length)
            return

        end = start + 1
        while end < length:
            if text[end] == "$" and text[end - 1] != "\\":
                if end + 1 < length and text[end + 1] == "$":
                    end += 2
                    continue
                break
            end += 1

        if end >= length:
            yield ("text", text[cursor:], cursor, length)
            return

        if start > cursor:
            yield ("text", text[cursor:start], cursor, start)
        yield ("math", text[start + 1:end], start, end + 1)
        cursor = end + 1


def _legacy_math_is_standalone(text: str, start: int, end: int) -> bool:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end < 0:
        line_end = len(text)
    return text[line_start:line_end].strip() == text[start:end].strip()


class DocumentAssemblyError(DocumentModelError):
    """Raised when authoring output cannot be assembled safely."""


def _assert_authoring_math_integrity(authoring_text: str) -> None:
    math_issues = audit_authoring_math_integrity(authoring_text)
    if math_issues:
        raise DocumentAssemblyError(
            "Authoring text violates semantic math integrity: "
            + "; ".join(issue.format() for issue in math_issues)
        )


def _stable_occurrence_id(
    section_id: str,
    segment_index: int,
    marker_type: str,
    identifier: str,
) -> str:
    """Return a stable occurrence UUID for one document location."""
    key = f"{section_id}|{segment_index}|{marker_type}|{identifier}"
    return str(uuid.uuid5(_OCCURRENCE_NAMESPACE, key))


def _citation_cluster_source_ids(identifier: str) -> tuple[str, ...]:
    source_ids = tuple(part.strip() for part in str(identifier).split(","))
    if len(source_ids) < 2 or any(not source_id for source_id in source_ids):
        raise DocumentAssemblyError(
            "CITES marker must contain at least two comma-separated source IDs."
        )
    if len(set(source_ids)) != len(source_ids):
        raise DocumentAssemblyError("CITES marker must not contain duplicate source IDs.")
    return source_ids


def _validate_marker_references(
    segments: List[object],
    *,
    equation_ids: Set[str],
    source_ids: Set[str],
    target_ids: Set[str],
    proposal_ids: Set[str],
) -> None:
    """Validate semantic marker identifiers against authoritative registries."""
    for segment in segments:
        if isinstance(segment, TextSegment):
            continue
        if not isinstance(segment, SemanticMarker):
            raise DocumentAssemblyError(
                f"Unsupported authoring segment: {type(segment).__name__}."
            )

        marker_type = segment.marker_type
        identifier = segment.identifier

        if marker_type == "CITE":
            if identifier not in source_ids:
                raise DocumentAssemblyError(
                    f"Unknown citation source_id: {identifier}."
                )
        elif marker_type == "CITES":
            for citation_source_id in _citation_cluster_source_ids(identifier):
                if citation_source_id not in source_ids:
                    raise DocumentAssemblyError(
                        f"Unknown citation source_id: {citation_source_id}."
                    )
        elif marker_type == "REF":
            if identifier not in target_ids:
                raise DocumentAssemblyError(
                    f"Unknown cross-reference target_id: {identifier}."
                )
        elif marker_type == "EQ":
            if identifier not in equation_ids:
                raise DocumentAssemblyError(
                    f"Unknown equation_id: {identifier}."
                )
        elif marker_type == "NEW_EQ":
            if identifier not in proposal_ids:
                raise DocumentAssemblyError(
                    f"Unknown equation proposal_id: {identifier}."
                )
        else:
            raise DocumentAssemblyError(
                f"Unsupported semantic marker type: {marker_type}."
            )


def validate_authoring_text(
    authoring_text: str,
    *,
    equation_ids: Set[str],
    source_ids: Set[str],
    target_ids: Set[str],
    proposal_ids: Optional[Set[str]] = None,
) -> None:
    """Validate authoring syntax and referenced semantic identifiers.

    Validation performs no semantic-object construction and assigns no
    document-location occurrence identifiers. It raises ``DocumentAssemblyError``
    when a parsed marker references an identifier outside the supplied registries.
    """
    equation_ids = set(equation_ids or set())
    source_ids = set(source_ids or set())
    target_ids = set(target_ids or set())
    proposal_ids = set(proposal_ids or set())

    _assert_authoring_math_integrity(authoring_text)

    segments = parse_authoring_text(authoring_text)
    _validate_marker_references(
        segments,
        equation_ids=equation_ids,
        source_ids=source_ids,
        target_ids=target_ids,
        proposal_ids=proposal_ids,
    )


def assemble_section(
    *,
    section_id: str,
    title: str,
    authoring_text: str,
    equation_ids: Set[str],
    source_ids: Set[str],
    target_ids: Set[str],
    proposal_ids: Optional[Set[str]] = None,
    parent_section_ids: Optional[List[str]] = None,
    status: Optional[str] = None,
    generated_from: Optional[str] = None,
    subsection_index: Optional[int] = None,
    parse_legacy_math: bool = False,
) -> Section:
    """Assemble one writer result into an ordered semantic document section.

    ``EQ`` markers become display-equation occurrences and therefore split
    paragraphs. ``CITE`` and ``REF`` remain inline. ``NEW_EQ`` creates a
    non-renderable proposal reference and requires the proposal to be present
    in ``proposal_ids``.
    """
    if not isinstance(section_id, str) or not section_id.strip():
        raise DocumentAssemblyError("section_id must be non-empty.")
    if not isinstance(title, str) or not title.strip():
        raise DocumentAssemblyError("title must be non-empty.")

    equation_ids = set(equation_ids or set())
    source_ids = set(source_ids or set())
    target_ids = set(target_ids or set())
    proposal_ids = set(proposal_ids or set())

    _assert_authoring_math_integrity(authoring_text)

    segments = parse_authoring_text(authoring_text)
    _validate_marker_references(
        segments,
        equation_ids=equation_ids,
        source_ids=source_ids,
        target_ids=target_ids,
        proposal_ids=proposal_ids,
    )

    children = []
    inline_nodes = []

    def flush_paragraph() -> None:
        if inline_nodes:
            children.append(Paragraph(inline_content=list(inline_nodes)))
            inline_nodes.clear()

    def append_text_segment(text: str) -> None:
        if not parse_legacy_math:
            if text:
                inline_nodes.append(Text(text))
            return

        for fragment_type, payload, start, end in _iter_legacy_math(text):
            if not payload:
                continue
            if fragment_type == "text":
                inline_nodes.append(Text(payload))
                continue

            if _legacy_math_is_standalone(text, start, end):
                flush_paragraph()
                children.append(DisplayMath(payload))
            else:
                inline_nodes.append(InlineMath(payload))

    for segment_index, segment in enumerate(segments):
        if isinstance(segment, TextSegment):
            append_text_segment(segment.text)
            continue

        if not isinstance(segment, SemanticMarker):
            raise DocumentAssemblyError(
                f"Unsupported authoring segment: {type(segment).__name__}."
            )

        marker_type = segment.marker_type
        identifier = segment.identifier
        occurrence_id = _stable_occurrence_id(
            section_id,
            segment_index,
            marker_type,
            identifier,
        )

        if marker_type == "CITE":
            inline_nodes.append(
                CitationOccurrence(
                    source_id=identifier,
                    occurrence_id=occurrence_id,
                )
            )

        elif marker_type == "CITES":
            inline_nodes.append(
                CitationClusterOccurrence(
                    source_ids=_citation_cluster_source_ids(identifier),
                    occurrence_id=occurrence_id,
                )
            )

        elif marker_type == "REF":
            inline_nodes.append(
                CrossReferenceOccurrence(
                    target_id=identifier,
                    occurrence_id=occurrence_id,
                )
            )

        elif marker_type == "EQ":
            flush_paragraph()
            children.append(
                EquationOccurrence(
                    equation_id=identifier,
                    occurrence_id=occurrence_id,
                )
            )

        elif marker_type == "NEW_EQ":
            flush_paragraph()
            children.append(
                EquationProposalReference(
                    proposal_id=identifier,
                    occurrence_id=occurrence_id,
                )
            )

        else:
            raise DocumentAssemblyError(
                f"Unsupported semantic marker type: {marker_type}."
            )

    flush_paragraph()

    return Section(
        title=title,
        children=children,
        section_id=section_id,
        parent_section_ids=list(parent_section_ids or []),
        status=status,
        generated_from=generated_from,
        subsection_index=subsection_index,
    )


def assemble_document_fragment(
    sections: Mapping[str, str],
    *,
    equation_ids: Set[str],
    source_ids: Set[str],
    target_ids: Set[str],
    proposal_ids: Optional[Set[str]] = None,
) -> List[Section]:
    """Assemble multiple ``section_id -> authoring_text`` pairs deterministically.

    Section ordering follows insertion order of the supplied mapping.
    Callers that need explicit ordering should supply an ordered mapping or
    construct the sections individually.
    """
    result = []
    for section_id, authoring_text in sections.items():
        result.append(
            assemble_section(
                section_id=section_id,
                title=section_id,
                authoring_text=authoring_text,
                equation_ids=equation_ids,
                source_ids=source_ids,
                target_ids=target_ids,
                proposal_ids=proposal_ids,
            )
        )
    return result
