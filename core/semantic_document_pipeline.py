#!/usr/bin/env python3
"""Shadow semantic-document integration for migration to canonical publication IR."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re
from typing import Any, Dict, Mapping, Sequence
import uuid

from core.document_model import (
    CitationOccurrence,
    CrossReferenceOccurrence,
    DisplayMath,
    Document,
    EquationOccurrence,
    EquationProposalReference,
    InlineMath,
    Paragraph,
    Text,
)
from core.document_persistence import save_document
from core.domain_semantic_model import get_authorized_equation_ids
from writing.section_document_adapter import legacy_section_to_document_section
from writing.semantic_authoring_shadow import annotate_legacy_authoring


_SEMANTIC_DOCUMENT_NAMESPACE = uuid.UUID("10381eed-bb45-4f7a-89ec-d894b112e1ab")
_RAW_INLINE_MATH_RE = re.compile(r"(?<!\\)\$(?!\$).+?(?<!\\)\$", flags=re.DOTALL)


def analyze_latex_ir_readiness(document: Document) -> Dict[str, Any]:
    """Describe whether semantic publication content is structurally IR-ready.

    Readiness here means that legacy dollar-delimited mathematics is no longer
    hidden inside ``Text`` nodes and that no unresolved equation proposal is
    present.  It deliberately does not claim that the current LaTeX IR already
    has matching block types; that is the next boundary.
    """
    counts = {
        "sections": 0,
        "paragraphs": 0,
        "text_nodes": 0,
        "inline_math": 0,
        "display_math": 0,
        "equation_occurrences": 0,
        "citation_occurrences": 0,
        "cross_reference_occurrences": 0,
        "equation_proposal_references": 0,
        "raw_math_text_nodes": 0,
    }
    diagnostics: list[str] = []

    for section in document.children:
        counts["sections"] += 1
        for child in section.children:
            if isinstance(child, Paragraph):
                counts["paragraphs"] += 1
                for node in child.inline_content:
                    if isinstance(node, Text):
                        counts["text_nodes"] += 1
                        if _RAW_INLINE_MATH_RE.search(node.text):
                            counts["raw_math_text_nodes"] += 1
                            diagnostics.append(
                                f"raw_math_in_text:{section.section_id}"
                            )
                    elif isinstance(node, InlineMath):
                        counts["inline_math"] += 1
                    elif isinstance(node, CitationOccurrence):
                        counts["citation_occurrences"] += 1
                    elif isinstance(node, CrossReferenceOccurrence):
                        counts["cross_reference_occurrences"] += 1
            elif isinstance(child, DisplayMath):
                counts["display_math"] += 1
            elif isinstance(child, EquationOccurrence):
                counts["equation_occurrences"] += 1
            elif isinstance(child, EquationProposalReference):
                counts["equation_proposal_references"] += 1
                diagnostics.append(
                    f"unresolved_equation_proposal:{section.section_id}:{child.proposal_id}"
                )

    ready = (
        counts["raw_math_text_nodes"] == 0
        and counts["equation_proposal_references"] == 0
    )
    return {
        "ready": ready,
        "counts": counts,
        "diagnostics": diagnostics,
    }


def _document_id(state: Dict[str, Any]) -> str:
    existing = state.get("semantic_candidate_document_id")
    if isinstance(existing, str) and existing.strip():
        return existing
    seed = f"{state.get('topic', '')}|{state.get('objective', '')}"
    generated = str(uuid.uuid5(_SEMANTIC_DOCUMENT_NAMESPACE, seed))
    state["semantic_candidate_document_id"] = generated
    return generated


def build_semantic_candidate_document(
    state: Dict[str, Any],
    *,
    evidence: Sequence[Mapping[str, Any]],
) -> tuple[Document, Dict[str, Any]]:
    """Build a non-authoritative semantic candidate without mutating sections."""
    sections = state.get("sections", [])
    if not isinstance(sections, list):
        sections = []

    domain_model = state.get("domain_semantic_model", {})
    equation_ids = get_authorized_equation_ids(domain_model)
    source_ids = {
        str(item.get("source_id"))
        for item in evidence
        if isinstance(item, Mapping) and item.get("source_id")
    }

    semantic_sections = []
    section_reports = []

    for raw_section in sections:
        if not isinstance(raw_section, dict):
            continue
        shadow = annotate_legacy_authoring(
            str(raw_section.get("content", "")),
            domain_model=domain_model,
            source_ids=source_ids,
        )
        shadow_section = deepcopy(raw_section)
        shadow_section["content"] = shadow.authoring_text

        semantic_section = legacy_section_to_document_section(
            shadow_section,
            equation_ids=equation_ids,
            source_ids=source_ids,
            target_ids=set(),
            proposal_ids=set(),
            parse_inline_math=True,
        )
        semantic_sections.append(semantic_section)

        inline_math_count = 0
        display_math_count = 0
        equation_occurrence_count = 0
        for child in semantic_section.children:
            if isinstance(child, Paragraph):
                inline_math_count += sum(
                    isinstance(node, InlineMath)
                    for node in child.inline_content
                )
            elif isinstance(child, DisplayMath):
                display_math_count += 1
            elif isinstance(child, EquationOccurrence):
                equation_occurrence_count += 1

        section_reports.append(
            {
                "section_id": semantic_section.section_id,
                "semantic_marker_count": (
                    len(shadow.annotated_equation_ids)
                    + len(shadow.annotated_source_ids)
                ),
                "annotated_equation_ids": list(shadow.annotated_equation_ids),
                "annotated_source_ids": list(shadow.annotated_source_ids),
                "inline_math_count": inline_math_count,
                "display_math_count": display_math_count,
                "equation_occurrence_count": equation_occurrence_count,
                "diagnostics": list(shadow.diagnostics),
            }
        )

    report = {
        "status": "candidate",
        "authoritative_for_rendering": False,
        "sections": section_reports,
        "semantic_marker_count": sum(
            int(item["semantic_marker_count"]) for item in section_reports
        ),
    }
    document = Document(
        children=semantic_sections,
        document_id=_document_id(state),
        metadata={
            "publication_role": "semantic_candidate",
            "authoritative_for_rendering": False,
        },
        source_snapshot={
            "legacy_section_ids": [
                section.get("section_id")
                for section in sections
                if isinstance(section, dict) and section.get("section_id")
            ]
        },
    )
    document.validate()
    readiness = analyze_latex_ir_readiness(document)
    report["latex_ir_readiness"] = readiness
    document.metadata["shadow_report"] = report
    document.metadata["latex_ir_readiness"] = readiness
    document.validate()
    return document, report


def persist_semantic_candidate_document(
    state: Dict[str, Any],
    paths: Mapping[str, Any],
    *,
    evidence: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Persist the shadow semantic candidate while leaving rendering untouched."""
    destination = paths.get("semantic_candidate_document")
    if destination is None:
        raise ValueError("Pipeline paths must define 'semantic_candidate_document'.")

    document, report = build_semantic_candidate_document(
        state,
        evidence=evidence,
    )
    save_document(document, Path(destination))
    state["semantic_candidate_status"] = report
    return report
