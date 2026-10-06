#!/usr/bin/env python3
"""Derive a deterministic LaTeX capability set from renderer-neutral IR.

The resolver is intentionally publication-only: it observes declared IR block
kinds and typed math payloads, never runtime application state or scientific
meaning.  Package ordering is centralized so the generated preamble is minimal
and reproducible for a given DocumentModel.
"""

from __future__ import annotations

from dataclasses import dataclass

from processing.latex_ir import (
    CitationBlock,
    ConceptGraphBlock,
    DocumentModel,
    EquationBlock,
    FigureBlock,
    IRCitationSpan,
    IRMathSpan,
    MathBlock,
    ParagraphBlock,
    RelationshipTableBlock,
    TableBlock,
)


@dataclass(frozen=True)
class LatexCapabilities:
    has_math: bool = False
    needs_amsfonts: bool = False
    needs_bm: bool = False
    needs_mathtools: bool = False
    has_citations: bool = False
    has_figures: bool = False
    has_tables: bool = False
    has_concept_graph: bool = False
    has_relationship_table: bool = False


def analyze_latex_capabilities(document: DocumentModel) -> LatexCapabilities:
    math_expressions: list[str] = []
    has_citations = False
    has_figures = False
    has_tables = False
    has_concept_graph = False
    has_relationship_table = False

    for section in document.sections:
        for block in section.blocks:
            if isinstance(block, (MathBlock, EquationBlock)):
                math_expressions.append(block.expression)
            elif isinstance(block, ParagraphBlock):
                for inline in block.content:
                    if isinstance(inline, IRMathSpan):
                        math_expressions.append(inline.expression)
                    elif isinstance(inline, IRCitationSpan):
                        has_citations = True
            elif isinstance(block, CitationBlock):
                has_citations = True
            elif isinstance(block, FigureBlock):
                has_figures = True
                has_citations = has_citations or bool(block.source_ids)
            elif isinstance(block, TableBlock):
                has_tables = True
                has_citations = has_citations or bool(block.source_ids)
            elif isinstance(block, ConceptGraphBlock):
                has_concept_graph = True
            elif isinstance(block, RelationshipTableBlock):
                has_relationship_table = True

    joined = "\n".join(math_expressions)
    return LatexCapabilities(
        has_math=bool(math_expressions),
        needs_amsfonts=(r"\mathbb" in joined or r"\mathfrak" in joined),
        needs_bm=(r"\bm" in joined),
        needs_mathtools=any(
            token in joined
            for token in (
                r"\coloneqq",
                r"\mathclap",
                r"\mathllap",
                r"\mathrlap",
                r"\DeclarePairedDelimiter",
            )
        ),
        has_citations=has_citations,
        has_figures=has_figures,
        has_tables=has_tables,
        has_concept_graph=has_concept_graph,
        has_relationship_table=has_relationship_table,
    )


def render_package_lines(document: DocumentModel) -> tuple[str, ...]:
    """Return package lines in a stable dependency-safe order."""
    capabilities = analyze_latex_capabilities(document)
    lines: list[str] = [
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{lmodern}",
    ]

    math_packages: list[str] = []
    if capabilities.has_math:
        math_packages.extend(["amsmath", "amssymb"])
        if capabilities.needs_amsfonts:
            math_packages.append("amsfonts")
        if capabilities.needs_bm:
            math_packages.append("bm")
        if capabilities.needs_mathtools:
            math_packages.append("mathtools")
    if math_packages:
        lines.append(r"\usepackage{" + ", ".join(math_packages) + "}")

    lines.extend([
        r"\usepackage{geometry}",
        r"\usepackage{microtype}",
        # Provenance is always rendered as a longtable.
        r"\usepackage{booktabs}",
        r"\usepackage{longtable}",
        r"\usepackage{array}",
    ])

    if capabilities.has_figures:
        lines.append(r"\usepackage{graphicx}")
    if capabilities.has_figures or capabilities.has_tables:
        lines.append(r"\usepackage{float}")
    if capabilities.has_tables:
        lines.append(r"\usepackage{tabularx}")
    if capabilities.has_concept_graph:
        lines.append(r"\usepackage{tikz}")
        lines.append(r"\usetikzlibrary{arrows.meta}")
    if capabilities.has_citations:
        lines.append(r"\usepackage{cite}")

    # Load hyperref after ordinary content packages. It is always required by
    # URL/provenance rendering and provides stable document links.
    lines.append(r"\usepackage{hyperref}")
    return tuple(lines)
