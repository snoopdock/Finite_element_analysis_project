#!/usr/bin/env python3
"""LaTeX document building utilities with provenance tracking."""

from processing.latex_capabilities import render_package_lines
from processing.latex_ir import (
    CitationBlock,
    DocumentModel,
    FigureBlock,
    IRCitationSpan,
    ParagraphBlock,
    TableBlock,
    build_document_model,
    validate_document_model,
)
from processing.latex_references import format_bibliography, format_provenance_table
from processing.latex_renderer import render_body
from processing.publication_integrity import assert_publication_integrity
from utils.latex import escape_text


def _cited_source_ids(document: DocumentModel) -> tuple[str, ...]:
    """Return source identities in first semantic citation-occurrence order."""
    ordered: list[str] = []
    seen: set[str] = set()

    def add(source_ids) -> None:
        for source_id in source_ids:
            if source_id not in seen:
                seen.add(source_id)
                ordered.append(source_id)

    for section in document.sections:
        for block in section.blocks:
            if isinstance(block, ParagraphBlock):
                for inline in block.content:
                    if isinstance(inline, IRCitationSpan):
                        add(inline.source_ids)
            elif isinstance(block, CitationBlock):
                add(block.source_ids)
            elif isinstance(block, (FigureBlock, TableBlock)):
                add(block.source_ids)
    return tuple(ordered)


def build_latex_document(state, sections, evidence):
    """Compatibility entry point for legacy IR dictionaries."""
    document = build_document_model(state, sections, evidence)
    return build_latex_document_from_model(state, document)


def build_latex_document_from_model(_state, document: DocumentModel):
    """Build complete LaTeX from an already-projected renderer-neutral model."""
    validate_document_model(document)
    topic = document.topic
    objective = document.objective

    # Bibliography is a projection of semantic citation occurrences only.
    # Provenance remains the complete retrieval receipt.
    reference_by_id = {reference.source_id: reference for reference in document.references}
    cited_references = tuple(
        reference_by_id[source_id] for source_id in _cited_source_ids(document)
    )
    refs_text = format_bibliography(cited_references)
    provenance_table = format_provenance_table(document.references)

    body = render_body(document)

    doc_lines = [
        r"\documentclass[12pt, a4paper]{article}",
        *render_package_lines(document),
        r"\geometry{margin=1in}",
        "",
        r"% Conservative line-breaking allowance without global paragraph relaxation",
        r"\setlength{\emergencystretch}{3em}",
        "",
        r"\hypersetup{colorlinks=true, linkcolor=blue, citecolor=blue, urlcolor=blue}",
        "",
        r"\title{" + escape_text(topic) + r"}",
        r"\author{Automated Scientific Pipeline}",
        r"\date{}",
        "",
        r"\begin{document}",
        "",
        r"\maketitle",
        r"\tableofcontents",
        r"\newpage",
        "",
        r"\section{Objective}",
        escape_text(objective),
        "",
    ]

    doc_lines.extend([body, ""])

    if refs_text:
        bibliography_width = "9" * max(1, len(str(len(cited_references))))
        doc_lines.extend([
            rf"\begin{{thebibliography}}{{{bibliography_width}}}",
            r"\raggedright",
            refs_text,
            r"\end{thebibliography}",
            "",
        ])

    doc_lines.extend([
        r"\newpage",
        r"\section*{Appendix: Source Provenance}",
        r"\addcontentsline{toc}{section}{Appendix: Source Provenance}",
        r"\small",
        r"The following table provides the complete retrieval receipt for each source retained in the document evidence registry.",
        r"It records when each source was fetched, from which provider, and its unique identifier.",
        r"\vspace{1em}",
        r"",
        r"\begin{longtable}{@{}"
        r">{\raggedright\arraybackslash}p{0.5cm} "
        r">{\raggedright\arraybackslash}p{3.1cm} "
        r">{\raggedright\arraybackslash}p{5.7cm} "
        r">{\raggedright\arraybackslash}p{2.0cm} "
        r">{\raggedright\arraybackslash}p{2.7cm} @{}}",
        r"\toprule",
        r"\textbf{\#} & \textbf{Source ID} & \textbf{Title} & \textbf{Type} & \textbf{Retrieved At} \\",
        r"\midrule",
        r"\endfirsthead",
        r"\toprule",
        r"\textbf{\#} & \textbf{Source ID} & \textbf{Title} & \textbf{Type} & \textbf{Retrieved At} \\",
        r"\midrule",
        r"\endhead",
        r"\bottomrule",
        r"\endfoot",
        provenance_table,
        r"\end{longtable}",
        r"",
        r"\normalsize",
        r"",
        r"\end{document}",
    ])
    tex = "\n".join(doc_lines)
    assert_publication_integrity(document, tex)
    return tex
