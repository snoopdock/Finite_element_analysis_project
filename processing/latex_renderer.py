"""Rendering helpers for the semantic document model.

This module owns translation from renderer-neutral blocks to LaTeX. Legacy
fragments are intentionally rendered without plain-text escaping because they
are already-authored LaTeX and are isolated by the semantic model.
"""

from __future__ import annotations

from processing.latex_ir import DocumentModel, LegacyLatexBlock, MathBlock, TextBlock
from utils.latex import escape_latex, escape_text, sanitize_latex_content


def render_block(block: TextBlock | MathBlock | LegacyLatexBlock) -> str:
    """Render one semantic block into LaTeX according to its declared kind."""
    if isinstance(block, TextBlock):
        return escape_text(block.text)
    if isinstance(block, MathBlock):
        expression = block.expression.strip()
        if not expression:
            return ""
        return f"\\[{expression}\\]"
    if isinstance(block, LegacyLatexBlock):
        return sanitize_latex_content(block.source)
    raise TypeError(f"Unsupported document block: {type(block).__name__}")


def render_section(section) -> str:
    """Render a semantic section, omitting empty blocks."""
    rendered = [render_block(block) for block in section.blocks]
    content = "\n\n".join(part for part in rendered if part.strip())
    if not content:
        return ""
    return f"\\section{{{escape_latex(section.title)}}}\n\n{content}"


def render_body(document: DocumentModel) -> str:
    """Render all document sections in order."""
    sections = [render_section(section) for section in document.sections]
    sections = [section for section in sections if section.strip()]
    return "\n\n".join(sections) if sections else "% No content generated."
