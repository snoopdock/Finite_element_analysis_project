"""Rendering helpers for the semantic document model.

This module owns translation from renderer-neutral blocks to LaTeX. Legacy
fragments are intentionally rendered without plain-text escaping because they
are already-authored LaTeX and are isolated by the semantic model.
"""

from __future__ import annotations

from processing.latex_ir import (
    CitationBlock,
    DocumentModel,
    DocumentModelError,
    LegacyLatexBlock,
    MathBlock,
    TextBlock,
    validate_document_model,
)
from utils.latex import escape_text, sanitize_latex_content


def render_block(block, reference_numbers: dict[str, str] | None = None) -> str:
    """Render one semantic block into LaTeX according to its declared kind."""
    if isinstance(block, TextBlock):
        return escape_text(block.text)
    if isinstance(block, MathBlock):
        expression = block.expression.strip()
        if not expression:
            return ""
        return f"\\[{expression}\\]"
    if isinstance(block, CitationBlock):
        if not reference_numbers:
            raise DocumentModelError(
                "cannot render citation without a reference-number mapping"
            )
        missing = [
            source_id
            for source_id in block.source_ids
            if source_id not in reference_numbers
        ]
        if missing:
            raise DocumentModelError(
                "citation references unknown source_id(s): " + ", ".join(missing)
            )
        keys = [reference_numbers[source_id] for source_id in block.source_ids]
        return f"\\cite{{{','.join(keys)}}}"
    if isinstance(block, LegacyLatexBlock):
        return sanitize_latex_content(block.source)
    raise TypeError(f"Unsupported document block: {type(block).__name__}")


def render_section(section, reference_numbers: dict[str, str] | None = None) -> str:
    """Render a semantic section, omitting empty blocks."""
    rendered = [render_block(block, reference_numbers) for block in section.blocks]
    content = "\n\n".join(part for part in rendered if part.strip())
    if not content:
        return ""
    return f"\\section{{{escape_text(section.title)}}}\n\n{content}"


def render_body(document: DocumentModel) -> str:
    """Validate and render all document sections in order."""
    validate_document_model(document)
    reference_numbers = {
        reference.source_id: reference.citation_key
        for reference in document.references
        if reference.citation_key
    }
    sections = [render_section(section, reference_numbers) for section in document.sections]
    sections = [section for section in sections if section.strip()]
    return "\n\n".join(sections) if sections else "% No content generated."
