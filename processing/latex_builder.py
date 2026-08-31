#!/usr/bin/env python3
"""LaTeX document building utilities with provenance tracking."""

import sys
from datetime import datetime
from utils.latex import escape_latex, sanitize_latex_content
from processing.latex_graph import render_concept_graph, render_perspective_table


def build_latex_document(state, sections, evidence):
    topic = state.get("topic", "Finite Element Method Guideline")
    objective = state.get("objective", "")
    graph = state.get("knowledge_graph", {})

    # Build a clean, numbered bibliography
    refs = []
    for i, source in enumerate(evidence[:25]):
        title = escape_latex(source.get("title", "Unknown Title"))
        stype = source.get("retriever_module", "misc").replace("research.", "").title()
        url = source.get("url", "")
        url = url.replace("%", r"\%").replace("&", r"\&").replace("#", r"\#")
        refs.append(
            f"  \\bibitem{{ref{i + 1}}} \\textit{{{title}}}. [{stype}] Available at: \\url{{{url}}}"
        )

    refs_text = "\n".join(refs) if refs else "  \\bibitem{none} No sources retrieved."

    # Build the Provenance Appendix
    provenance_rows = []
    for i, source in enumerate(evidence[:25]):
        sid = escape_latex(source.get("source_id", "unknown"))
        title = escape_latex(source.get("title", "Unknown"))
        retrieved = source.get("retrieved_at", "N/A")
        url = source.get("url", "").replace("%", r"\%").replace("&", r"\&").replace("#", r"\#")
        stype = source.get("retriever_module", "misc").replace("research.", "").title()
        if retrieved != "N/A":
            try:
                dt = datetime.fromisoformat(retrieved.replace("Z", "+00:00"))
                retrieved = dt.strftime("%Y-%m-%d %H:%M UTC")
            except Exception:
                pass
        provenance_rows.append(
            f"  {i+1} & \\texttt{{{sid}}} & {title[:60]} & {stype} & {retrieved} \\\\"
        )

    provenance_table = "\n".join(provenance_rows) if provenance_rows else "No sources."

    body_parts = []
    for s in sections:
        content = s.get("content", "").strip()
        if not content:
            print(
                f"  [LaTeX] Warning: Skipping empty section '{s.get('title', 'Untitled')}'",
                file=sys.stderr,
            )
            continue
        sanitized_content = sanitize_latex_content(content)
        body_parts.append(
            "\\section{" + escape_latex(s.get("title", "Untitled")) +
            "}\n\n" + sanitized_content
        )
    body = "\n\n".join(body_parts) if body_parts else "% No content generated."

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
        r"\usepackage{enumitem}",
        r"\usepackage{newunicodechar}",
        r"\usepackage[strings]{underscore}",
        r"\usepackage{cite}",
        r"\usepackage{longtable}",
        r"\usepackage{array}",
        r"\usepackage{tikz}",
        r"\usetikzlibrary{positioning,arrows.meta}",
        "",
        r"% Fix layout warnings",
        r"\setlength{\emergencystretch}{3em}",
        r"\sloppy",
        "",
        r"% Math compatibility layer",
        r"\makeatletter",
        r"\newcommand{\@safemath}[1]{%",
        r"  \expandafter\let\csname orig@#1\expandafter\endcsname\csname #1\endcsname",
        r"  \expandafter\renewcommand\csname #1\endcsname{\ensuremath{\csname orig@#1\endcsname}}%",
        r"}",
        r"\@safemath{in}\@safemath{nabla}\@safemath{delta}\@safemath{partial}",
        r"\@safemath{int}\@safemath{sum}\@safemath{prod}",
        r"\@safemath{alpha}\@safemath{beta}\@safemath{gamma}\@safemath{sigma}",
        r"\@safemath{epsilon}\@safemath{omega}\@safemath{theta}\@safemath{lambda}\@safemath{mu}",
        r"\let\orig@mathbf\mathbf",
        r"\renewcommand{\mathbf}[1]{\ensuremath{\orig@mathbf{#1}}}",
        r"\makeatother",
        "",
        r"% Unicode safety net",
        r"\newunicodechar{∫}{\ensuremath{\int}}",
        r"\newunicodechar{∑}{\ensuremath{\sum}}",
        r"\newunicodechar{σ}{\ensuremath{\sigma}}",
        r"\newunicodechar{ε}{\ensuremath{\varepsilon}}",
        r"\newunicodechar{γ}{\ensuremath{\gamma}}",
        r"\newunicodechar{Ω}{\ensuremath{\Omega}}",
        r"\newunicodechar{∂}{\ensuremath{\partial}}",
        r"\newunicodechar{∇}{\ensuremath{\nabla}}",
        r"\newunicodechar{→}{\ensuremath{\rightarrow}}",
        r"\newunicodechar{⇒}{\ensuremath{\Rightarrow}}",
        r"\newunicodechar{≤}{\ensuremath{\le}}",
        r"\newunicodechar{≥}{\ensuremath{\ge}}",
        r"\newunicodechar{≠}{\ensuremath{\neq}}",
        r"\newunicodechar{≈}{\ensuremath{\approx}}",
        r"\newunicodechar{×}{\ensuremath{\times}}",
        "",
        r"\hypersetup{colorlinks=true, linkcolor=blue, citecolor=blue, urlcolor=blue}",
        "",
        r"\title{\textbf{" + escape_latex(topic) + r"}}",
        r"\author{Automated Scientific Pipeline}",
        r"\date{\today}",
        "",
        r"\begin{document}",
        "",
        r"\maketitle",
        r"\tableofcontents",
        r"\newpage",
        "",
        r"\section{Objective}",
        escape_latex(objective),
        "",
    ]

    if graph_has_nodes:
        doc_lines.extend([
            r"\section{Conceptual Map}",
            r"The following map shows the currently recorded concept structure. Concepts are maintained separately from propositions; edges are shown when the graph contains concept-to-concept relationships.",
            graph_map,
            "",
        ])

    doc_lines.extend([
        body,
        "",
    ])

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

    doc_lines.extend([
        r"\begin{thebibliography}{99}",
        refs_text,
        r"\end{thebibliography}",
        "",
        r"\newpage",
        r"\section*{Appendix: Source Provenance}",
        r"\addcontentsline{toc}{section}{Appendix: Source Provenance}",
        r"\small",
        r"The following table provides the complete retrieval receipt for each source used in this document.",
        r"It records when each source was fetched, from which provider, and its unique identifier.",
        r"\vspace{1em}",
        r"",
        r"\begin{longtable}{@{} p{0.5cm} p{3.5cm} p{5cm} p{1.5cm} p{3cm} @{}}",
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
    return "\n".join(doc_lines)
