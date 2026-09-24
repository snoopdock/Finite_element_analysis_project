"""Adapter between semantic writer sections and LaTeX IR sections.

The semantic writer produces rich document sections:
- title
- content
- key_equations
- citations_used

The LaTeX IR expects:
- title
- blocks

This module performs only transformation.
It does not validate scientific content.
"""

from typing import Any


def _paragraph_block(text: str) -> dict[str, Any]:
    return {
        "type": "text",
        "text": text.strip(),
    }


def _equation_block(equation: str) -> dict[str, Any]:
    return {
        "type": "math",
        "expression": equation.strip(),
    }


def _citation_block(citation_id: str) -> dict[str, Any]:
    return {
        "type": "citation",
        "source_ids": [citation_id.strip()],
    }


def adapt_section_to_latex_ir(section: dict[str, Any]) -> dict[str, Any]:
    """Convert one semantic section into LaTeX IR format."""

    if not isinstance(section, dict):
        raise TypeError("Section must be a dictionary.")

    title = section.get("title", "")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Section requires a non-empty title.")

    blocks = []

    content = section.get("content", "")
    if isinstance(content, str) and content.strip():
        blocks.append(_paragraph_block(content))

    equations = section.get("key_equations", [])
    if isinstance(equations, list):
        for equation in equations:
            if isinstance(equation, str) and equation.strip():
                blocks.append(_equation_block(equation))

    citations = section.get("citations_used", [])
    if isinstance(citations, list):
        for citation in citations:
            if isinstance(citation, str) and citation.strip():
                blocks.append(_citation_block(citation))

    return {
        "title": title.strip(),
        "blocks": blocks,
    }


def adapt_sections_to_latex_ir(
    sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert a list of semantic sections into LaTeX IR sections."""

    if not isinstance(sections, list):
        raise TypeError("Sections must be a list.")

    return [
        adapt_section_to_latex_ir(section)
        for section in sections
    ]
