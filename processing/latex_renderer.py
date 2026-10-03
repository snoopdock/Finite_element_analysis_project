"""Rendering helpers for the renderer-neutral LaTeX document model.

Plain prose is escaped. Mathematical spans and equations are rendered only
from typed IR nodes, so raw LaTeX is never recovered by scanning prose.
"""

from __future__ import annotations

import re

from processing.latex_ir import (
    CitationBlock,
    DocumentModel,
    DocumentModelError,
    EquationBlock,
    IRCitationSpan,
    IRMathSpan,
    IRTextSpan,
    LegacyLatexBlock,
    MathBlock,
    ParagraphBlock,
    TextBlock,
    validate_document_model,
)
from utils.latex import escape_text, sanitize_latex_content


def _citation_latex(
    source_ids: tuple[str, ...],
    reference_numbers: dict[str, str] | None,
) -> str:
    if not reference_numbers:
        raise DocumentModelError(
            "cannot render citation without a reference-number mapping"
        )
    missing = [
        source_id for source_id in source_ids if source_id not in reference_numbers
    ]
    if missing:
        raise DocumentModelError(
            "citation references unknown source_id(s): " + ", ".join(missing)
        )
    keys = [reference_numbers[source_id] for source_id in source_ids]
    return f"\\cite{{{','.join(keys)}}}"



def _render_label(label: str) -> str:
    """Return an explicit LaTeX label only when it is already label-safe."""
    if not re.fullmatch(r"[A-Za-z0-9:._/-]+", label):
        raise DocumentModelError(
            f"equation label contains unsupported LaTeX label characters: {label!r}"
        )
    return label

def render_inline(inline, reference_numbers: dict[str, str] | None = None) -> str:
    """Render one ordered paragraph-inline item."""
    if isinstance(inline, IRTextSpan):
        return escape_text(inline.text)
    if isinstance(inline, IRMathSpan):
        expression = inline.expression.strip()
        return f"\\({expression}\\)" if expression else ""
    if isinstance(inline, IRCitationSpan):
        return _citation_latex(inline.source_ids, reference_numbers)
    raise TypeError(f"Unsupported paragraph inline item: {type(inline).__name__}")


def render_block(block, reference_numbers: dict[str, str] | None = None) -> str:
    """Render one semantic block into LaTeX according to its declared kind."""
    if isinstance(block, TextBlock):
        return escape_text(block.text)
    if isinstance(block, ParagraphBlock):
        return "".join(
            render_inline(inline, reference_numbers) for inline in block.content
        )
    if isinstance(block, MathBlock):
        expression = block.expression.strip()
        if not expression:
            return ""
        return f"\\[{expression}\\]"
    if isinstance(block, EquationBlock):
        expression = block.expression.strip()
        if not expression:
            return ""
        parts = [r"\begin{equation}"]
        if block.label:
            parts.append(r"\label{" + _render_label(block.label) + "}")
        parts.append(expression)
        parts.append(r"\end{equation}")
        if block.caption:
            parts.extend(
                [
                    r"\begin{center}\small",
                    escape_text(block.caption),
                    r"\end{center}",
                ]
            )
        return "\n".join(parts)
    if isinstance(block, CitationBlock):
        return _citation_latex(block.source_ids, reference_numbers)
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
    sections = [
        render_section(section, reference_numbers) for section in document.sections
    ]
    sections = [section for section in sections if section.strip()]
    return "\n\n".join(sections) if sections else "% No content generated."
