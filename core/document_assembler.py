#!/usr/bin/env python3
"""Deterministic conversion from writer markers to document-model objects."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Set
import uuid

from core.document_model import (
    CitationOccurrence,
    CrossReferenceOccurrence,
    EquationOccurrence,
    EquationProposalReference,
    Paragraph,
    Section,
    Text,
    DocumentModelError,
)
from core.semantic_markers import SemanticMarker, TextSegment, parse_authoring_text


_OCCURRENCE_NAMESPACE = uuid.UUID("8e5e8d8d-84f0-4d1d-8d3f-2ce2d6ad6b25")


class DocumentAssemblyError(DocumentModelError):
    """Raised when authoring output cannot be assembled safely."""


def _stable_occurrence_id(
    section_id: str,
    segment_index: int,
    marker_type: str,
    identifier: str,
) -> str:
    """Return a stable occurrence UUID for one document location."""
    key = f"{section_id}|{segment_index}|{marker_type}|{identifier}"
    return str(uuid.uuid5(_OCCURRENCE_NAMESPACE, key))


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

    segments = parse_authoring_text(authoring_text)
    children = []
    inline_nodes = []

    def flush_paragraph() -> None:
        if inline_nodes:
            children.append(Paragraph(inline_content=list(inline_nodes)))
            inline_nodes.clear()

    for segment_index, segment in enumerate(segments):
        if isinstance(segment, TextSegment):
            if segment.text:
                inline_nodes.append(Text(segment.text))
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
            if identifier not in source_ids:
                raise DocumentAssemblyError(
                    f"Unknown citation source_id: {identifier}."
                )
            inline_nodes.append(
                CitationOccurrence(
                    source_id=identifier,
                    occurrence_id=occurrence_id,
                )
            )

        elif marker_type == "REF":
            if identifier not in target_ids:
                raise DocumentAssemblyError(
                    f"Unknown cross-reference target_id: {identifier}."
                )
            inline_nodes.append(
                CrossReferenceOccurrence(
                    target_id=identifier,
                    occurrence_id=occurrence_id,
                )
            )

        elif marker_type == "EQ":
            flush_paragraph()
            if identifier not in equation_ids:
                raise DocumentAssemblyError(
                    f"Unknown equation_id: {identifier}."
                )
            children.append(
                EquationOccurrence(
                    equation_id=identifier,
                    occurrence_id=occurrence_id,
                )
            )

        elif marker_type == "NEW_EQ":
            flush_paragraph()
            if identifier not in proposal_ids:
                raise DocumentAssemblyError(
                    f"Unknown equation proposal_id: {identifier}."
                )
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
