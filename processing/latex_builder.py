#!/usr/bin/env python3
"""LaTeX document building utilities with provenance tracking."""

from processing.latex_graph import render_concept_graph, render_perspective_table
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


def build_latex_document_from_model(state, document: DocumentModel):
    """Build complete LaTeX from an already-projected renderer-neutral model."""
    validate_document_model(document)
    topic = document.topic
    objective = document.objective
    graph = state.get("knowledge_graph", {})

    # Bibliography is a projection of semantic citation occurrences only.
    # Provenance remains the complete retrieval receipt.
    reference_by_id = {reference.source_id: reference for reference in document.references}
    cited_references = tuple(
        reference_by_id[source_id] for source_id in _cited_source_ids(document)
    )
    refs_text = format_bibliography(cited_references)
    provenance_table = format_provenance_table(document.references)

    body = render_body(document)

    graph_map = render_concept_graph(graph, max_nodes=40)
    perspective_table = render_perspective_table(graph, max_rows=30)
    graph_has_nodes = bool(graph.get("concepts")) if isinstance(graph, dict) else False
    graph_has_relationships = bool(graph.get("relationships")) if isinstance(graph, dict) else False

    doc_lines = [
        r"\documentclass[12pt, a4paper]{article}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{lmodern}",
        r"\usepackage{amsmath, amssymb, amsfonts, bm, mathtools}",
        r"\usepackage{geometry}",
        r"\geometry{margin=1in}",
        r"\usepackage{microtype}",
        r"\usepackage{hyperref}",
        r"\usepackage{booktabs}",
        r"\usepackage{graphicx}",
        r"\usepackage{float}",
        r"\usepackage{tabularx}",
        r"\usepackage{enumitem}",
        r"\usepackage{cite}",
        r"\usepackage{longtable}",
        r"\usepackage{array}",
        r"\usepackage{tikz}",
        r"\usetikzlibrary{positioning,arrows.meta}",
        "",
        r"% Conservative line-breaking allowance without global paragraph relaxation",
        r"\setlength{\emergencystretch}{3em}",
        "",
        r"\hypersetup{colorlinks=true, linkcolor=blue, citecolor=blue, urlcolor=blue}",
        "",
        r"\title{\textbf{" + escape_text(topic) + r"}}",
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

    if graph_has_nodes:
        doc_lines.extend([
            r"\section{Conceptual Map}",
            r"The following map shows the currently recorded concept structure. Concepts are maintained separately from propositions; edges are shown when the graph contains concept-to-concept relationships.",
            graph_map,
            "",
        ])

    doc_lines.extend([body, ""])

    if graph_has_relationships:
        doc_lines.extend([
            r"\newpage",
            r"\section*{Appendix: Scientific Perspectives and Relationships}",
            r"\addcontentsline{toc}{section}{Appendix: Scientific Perspectives and Relationships}",
            r"The table below preserves relationships among recorded propositions. A disagreement is not treated as an error solely because the propositions differ; contextual interpretation is retained in the relationship metadata.",
            r"\vspace{1em}",
            perspective_table,
            "",
        ])

    if refs_text:
        doc_lines.extend([
            r"\begin{thebibliography}{99}",
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
        r"The following table provides the complete retrieval receipt for each source used in this document.",
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
        r"\vspace{1em}",
        r"\textbf{Information Type Classification:}",
        r"\begin{itemize}",
        r"  \item \textbf{General Knowledge}: Textbook-level facts common across FEM literature. No specific citation required.",
        r"  \item \textbf{Attributed Knowledge}: Specific claims borrowed from another author's work. Cited with source reference.",
        r"  \item \textbf{Novel Contribution}: Original results unique to the source paper. Cited as primary source.",
        r"  \item \textbf{Synthesized Knowledge}: Conclusions derived by combining multiple sources. All contributing sources cited.",
        r"\end{itemize}",
        r"",
        r"\end{document}",
    ])
    tex = "\n".join(doc_lines)
    assert_publication_integrity(document, tex)
    return tex
