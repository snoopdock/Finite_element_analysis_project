#!/usr/bin/env python3
"""Rendering boundary for structured documents.

Legacy callers may still supply normalized section/reference mappings. The
canonical semantic path now projects ``core.document_model.Document`` into a
``processing.latex_ir.DocumentModel`` before entering this module.
"""

from typing import Any, Mapping, Sequence

from processing.latex_ir import DocumentModel


def render_document(
    state: Mapping[str, Any],
    sections: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
) -> str:
    """Compatibility renderer for legacy LaTeX-IR dictionaries."""
    from processing.latex_builder import build_latex_document

    return build_latex_document(state, sections, evidence)


def render_document_model(
    state: Mapping[str, Any],
    document: DocumentModel,
) -> str:
    """Render an already-projected canonical LaTeX IR document."""
    from processing.latex_builder import build_latex_document_from_model

    return build_latex_document_from_model(state, document)
