#!/usr/bin/env python3
"""Compatibility adapter between legacy writer sections and the document model.

The adapter is deliberately narrow. It preserves section identity and lineage,
converts legacy free-form content into prose, and projects semantic sections
back into the legacy dictionary shape for callers that still depend on it.
It does not infer equations or citations from legacy metadata.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from core.document_model import Document, DocumentModelError, Section, document_from_legacy_sections
from core.document_assembler import assemble_section
from core.section_identity import ensure_section_id


def legacy_sections_to_document(
    sections: Sequence[Dict[str, Any]],
    *,
    document_id: Optional[str] = None,
) -> Document:
    """Convert legacy section dictionaries into the semantic document model.

    Legacy ``content`` remains opaque prose. Legacy ``key_equations`` and
    ``citations_used`` are intentionally not reconstructed as semantic objects,
    because those fields are derived text scans rather than authoritative
    semantic references.
    """
    return document_from_legacy_sections(
        sections,
        document_id=document_id,
    )


def legacy_section_to_document_section(
    section: Dict[str, Any],
    *,
    equation_ids: Optional[Set[str]] = None,
    source_ids: Optional[Set[str]] = None,
    target_ids: Optional[Set[str]] = None,
    proposal_ids: Optional[Set[str]] = None,
) -> Section:
    """Convert one writer section, using semantic markers when explicitly present.

    A section containing semantic markers is assembled through the strict marker
    protocol. Otherwise its legacy ``content`` is preserved as one free-form
    paragraph. This prevents accidental inference from legacy citation/equation
    metadata.
    """
    if not isinstance(section, dict):
        raise DocumentModelError("Legacy section must be a dictionary.")

    section_id_holder = {"section_id": section.get("section_id")}
    section_id = ensure_section_id(section_id_holder)
    title = str(section.get("title", "Untitled"))
    content = section.get("content", "")
    if not isinstance(content, str):
        content = str(content)

    marker_present = "[[" in content
    common = {
        "section_id": section_id,
        "title": title,
        "equation_ids": set(equation_ids or set()),
        "source_ids": set(source_ids or set()),
        "target_ids": set(target_ids or set()),
        "proposal_ids": set(proposal_ids or set()),
        "parent_section_ids": list(section.get("parent_section_ids", []) or []),
        "status": section.get("status"),
        "generated_from": section.get("generated_from"),
        "subsection_index": section.get("subsection_index"),
    }

    if marker_present:
        return assemble_section(
            authoring_text=content,
            **common,
        )

    converted = document_from_legacy_sections(
        [section],
    )
    result = converted.children[0]
    result.document_id = getattr(result, "document_id", None)  # type: ignore[attr-defined]
    return result


def document_section_to_legacy(
    section: Section,
    *,
    include_derived_metadata: bool = True,
) -> Dict[str, Any]:
    """Project a semantic section into the legacy writer dictionary shape.

    The compatibility fields are projections only. They must not be treated as
    semantic authority by downstream components.
    """
    if not isinstance(section, Section):
        raise DocumentModelError("Expected a semantic document Section.")

    section.validate()

    paragraphs: List[str] = []
    equation_ids: List[str] = []
    citation_ids: List[str] = []

    for child in section.children:
        if child.type == "paragraph":
            parts: List[str] = []
            for node in child.inline_content:
                if node.type == "text":
                    parts.append(node.text)
                elif node.type == "citation_occurrence":
                    parts.append(f"[[CITE:{node.source_id}]]")
                    citation_ids.append(node.source_id)
                elif node.type == "cross_reference_occurrence":
                    parts.append(f"[[REF:{node.target_id}]]")
            paragraphs.append("".join(parts))
        elif child.type == "equation_occurrence":
            equation_ids.append(child.equation_id)
            paragraphs.append(f"[[EQ:{child.equation_id}]]")
        elif child.type == "equation_proposal_reference":
            paragraphs.append(f"[[NEW_EQ:{child.proposal_id}]]")
        else:
            raise DocumentModelError(
                f"Unsupported legacy projection child type: {child.type}."
            )

    data: Dict[str, Any] = {
        "section_id": section.section_id,
        "title": section.title,
        "content": "\n\n".join(paragraphs),
        "parent_section_ids": list(section.parent_section_ids),
    }

    if section.status is not None:
        data["status"] = section.status
    if section.generated_from is not None:
        data["generated_from"] = section.generated_from
    if section.subsection_index is not None:
        data["subsection_index"] = section.subsection_index

    if include_derived_metadata:
        data["key_equations"] = equation_ids[:5]
        data["citations_used"] = list(dict.fromkeys(citation_ids))

    return data


def document_to_legacy_sections(
    document: Document,
    *,
    include_derived_metadata: bool = True,
) -> List[Dict[str, Any]]:
    """Project all semantic document sections into legacy dictionaries."""
    document.validate()
    return [
        document_section_to_legacy(
            section,
            include_derived_metadata=include_derived_metadata,
        )
        for section in document.children
    ]
