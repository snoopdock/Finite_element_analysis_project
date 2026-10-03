#!/usr/bin/env python3
"""Canonical projection from semantic Document objects to LaTeX IR.

This module is the explicit boundary established by the L1-L23 architecture:

    core.document_model.Document -> processing.latex_ir.DocumentModel

The projection is deterministic and renderer-neutral.  It preserves document
order and occurrence identity, resolves authoritative equation payloads from
the domain semantic registry, and rejects unsupported/unresolved semantics
instead of guessing.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from core.document_model import (
    CitationOccurrence,
    CrossReferenceOccurrence,
    DisplayMath,
    Document,
    EquationOccurrence,
    EquationProposalReference,
    Figure,
    InlineMath,
    Paragraph,
    Table,
    Text,
    assert_renderable,
)
from core.domain_semantic_model import (
    get_authorized_equation_ids,
    resolve_equation,
)
from processing.evidence_adapter import adapt_evidence_to_references
from processing.latex_ir import (
    DocumentModel,
    EquationBlock,
    IRCitationSpan,
    IRMathSpan,
    IRTextSpan,
    MathBlock,
    ParagraphBlock,
    SectionModel,
    normalize_references,
    validate_document_model,
)


class DocumentToLatexIRError(ValueError):
    """Raised when a semantic document cannot be projected without loss."""


def _state_text(state: Mapping[str, Any], key: str, default: str = "") -> str:
    value = state.get(key, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise DocumentToLatexIRError(f"state.{key} must be a string")
    return value


def _project_paragraph(paragraph: Paragraph) -> ParagraphBlock | None:
    inline = []
    for node in paragraph.inline_content:
        if isinstance(node, Text):
            if node.text:
                inline.append(IRTextSpan(node.text))
        elif isinstance(node, InlineMath):
            inline.append(IRMathSpan(node.expression))
        elif isinstance(node, CitationOccurrence):
            inline.append(
                IRCitationSpan(
                    (node.source_id,),
                    occurrence_id=node.occurrence_id,
                )
            )
        elif isinstance(node, CrossReferenceOccurrence):
            # Cross-reference semantics require a document-wide label registry.
            # Until that boundary is implemented, rejecting is safer than
            # inventing a LaTeX label convention here.
            raise DocumentToLatexIRError(
                "CrossReferenceOccurrence projection requires the label registry "
                f"boundary; unsupported target_id={node.target_id!r}."
            )
        else:
            raise DocumentToLatexIRError(
                f"Unsupported paragraph node: {type(node).__name__}."
            )

    if not inline:
        return None
    return ParagraphBlock(tuple(inline))


def _reject_unsupported_semantics(document: Document) -> None:
    """Fail before registry validation when the IR has no lossless mapping yet."""
    for section in document.children:
        for child in section.children:
            if isinstance(child, Paragraph):
                for node in child.inline_content:
                    if isinstance(node, CrossReferenceOccurrence):
                        raise DocumentToLatexIRError(
                            "CrossReferenceOccurrence projection requires the label registry "
                            f"boundary; unsupported target_id={node.target_id!r}."
                        )
            elif isinstance(child, EquationProposalReference):
                raise DocumentToLatexIRError(
                    "Unresolved equation proposals cannot enter LaTeX IR: "
                    f"{child.proposal_id}."
                )
            elif isinstance(child, Figure):
                raise DocumentToLatexIRError(
                    "Figure projection is not implemented at the LaTeX IR boundary."
                )
            elif isinstance(child, Table):
                raise DocumentToLatexIRError(
                    "Table projection is not implemented at the LaTeX IR boundary."
                )


def project_document_to_latex_ir(
    document: Document,
    *,
    state: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]],
    domain_model: Mapping[str, Any],
) -> DocumentModel:
    """Project one validated semantic document into renderer-neutral LaTeX IR.

    Scientific equation payloads are resolved by ``equation_id`` from the
    domain semantic model. Evidence payloads are normalized from the evidence
    registry. The function never infers identity from labels, titles, or LaTeX
    strings.
    """
    if not isinstance(document, Document):
        raise DocumentToLatexIRError("document must be a semantic Document")
    if not isinstance(state, Mapping):
        raise DocumentToLatexIRError("state must be a mapping")
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)):
        raise DocumentToLatexIRError("evidence must be a sequence")
    if not isinstance(domain_model, Mapping):
        raise DocumentToLatexIRError("domain_model must be a mapping")

    document.validate()
    _reject_unsupported_semantics(document)

    normalized_evidence = adapt_evidence_to_references(list(evidence))
    references = normalize_references(normalized_evidence)
    source_ids = {reference.source_id for reference in references}
    equation_ids = get_authorized_equation_ids(domain_model)

    # The current production document has no cross references. Passing an empty
    # target registry makes any future REF occurrence fail closed until the
    # dedicated label registry is implemented.
    assert_renderable(
        document,
        equation_ids=equation_ids,
        source_ids=source_ids,
        target_ids=set(),
        proposal_ids=set(),
    )

    projected_sections: list[SectionModel] = []
    for section in document.children:
        blocks = []
        for child in section.children:
            if isinstance(child, Paragraph):
                paragraph = _project_paragraph(child)
                if paragraph is not None:
                    blocks.append(paragraph)
            elif isinstance(child, DisplayMath):
                blocks.append(MathBlock(child.expression))
            elif isinstance(child, EquationOccurrence):
                equation = resolve_equation(domain_model, child.equation_id)
                blocks.append(
                    EquationBlock(
                        equation_id=child.equation_id,
                        expression=str(equation["expression"]),
                        occurrence_id=child.occurrence_id,
                        label=child.label,
                        caption=child.caption,
                    )
                )
            elif isinstance(child, EquationProposalReference):
                # assert_renderable should already reject this. Keep the local
                # guard so future changes cannot accidentally make it lossy.
                raise DocumentToLatexIRError(
                    "Unresolved equation proposals cannot enter LaTeX IR: "
                    f"{child.proposal_id}."
                )
            elif isinstance(child, Figure):
                raise DocumentToLatexIRError(
                    "Figure projection is not implemented at the LaTeX IR boundary."
                )
            elif isinstance(child, Table):
                raise DocumentToLatexIRError(
                    "Table projection is not implemented at the LaTeX IR boundary."
                )
            else:
                raise DocumentToLatexIRError(
                    f"Unsupported section child: {type(child).__name__}."
                )

        projected_sections.append(
            SectionModel(
                title=section.title,
                blocks=tuple(blocks),
                section_id=section.section_id or "",
            )
        )

    projected = DocumentModel(
        topic=_state_text(
            state,
            "topic",
            default="Finite Element Method Guideline",
        ),
        objective=_state_text(state, "objective"),
        sections=tuple(projected_sections),
        references=references,
        source_document_id=document.document_id,
    )
    validate_document_model(projected)
    return projected
