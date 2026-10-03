#!/usr/bin/env python3
"""Shadow semantic-document integration for migration to canonical publication IR."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence
import uuid

from core.document_model import Document
from core.document_persistence import save_document
from core.domain_semantic_model import get_authorized_equation_ids
from writing.section_document_adapter import legacy_section_to_document_section
from writing.semantic_authoring_shadow import annotate_legacy_authoring


_SEMANTIC_DOCUMENT_NAMESPACE = uuid.UUID("10381eed-bb45-4f7a-89ec-d894b112e1ab")


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
        )
        semantic_sections.append(semantic_section)
        section_reports.append(
            {
                "section_id": semantic_section.section_id,
                "semantic_marker_count": (
                    len(shadow.annotated_equation_ids)
                    + len(shadow.annotated_source_ids)
                ),
                "annotated_equation_ids": list(shadow.annotated_equation_ids),
                "annotated_source_ids": list(shadow.annotated_source_ids),
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
            "shadow_report": report,
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
