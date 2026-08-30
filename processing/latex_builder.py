#!/usr/bin/env python3
"""LaTeX document building utilities."""

import sys
from utils.latex import escape_latex, sanitize_latex_content

def build_latex_document(state, sections, evidence):
    topic = state.get("topic", "Finite Element Method Guideline")
    objective = state.get("objective", "")

    refs = []
    for i, source in enumerate(evidence[:25]):
        title = escape_latex(source.get("title", "Unknown"))
        stype = source.get("source_type", "misc")
        
        # URLs often contain %, &, # which break LaTeX if not escaped
        url = source.get("url", "")
        url = url.replace("%", r"\%").replace("&", r"\&").replace("#", r"\#")
        
        refs.append(
            f"  \\bibitem{{ref{i + 1}}} {title}. [{stype}] \\url{{{url}}}"
        )
    refs_text = "\n".join(refs) if refs else "  \\bibitem{none} No sources retrieved."

    body_parts = []
    for s in sections:
        content = s.get("content", "").strip()
        if not content:
            print(f"  [LaTeX] Warning: Skipping empty section "
                  f"'{s.get('title', 'Untitled')}'", file=sys.stderr)
            continue

        # Sanitize LLM-generated prose (fixes Unicode math, $$, %, &)
        sanitized_content = sanitize_latex_content(content)

        body_parts.append(
            "\\section{" + escape_latex(s.get("title", "Untitled")) +
            "}\n\n" + sanitized_content
        )
    body = "\n\n".join(body_parts) if body_parts else "% No content generated."

    # UPGRADED PREAMBLE: Fixes layout warnings, adds math packages, and includes Unicode safety nets
        # UPGRADED PREAMBLE: Fixes layout warnings, scalable fonts, underscores, and math mode errors
    doc_lines = [
        r"\documentclass[12pt, a4paper]{article}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{lmodern}",  % FIX 1: Scalable fonts required for microtype
        r"\usepackage{amsmath, amssymb, amsfonts, bm, mathtools}",
        r"\usepackage{geometry}",
        r"\geometry{margin=1in}",
        r"\usepackage{microtype}",
        r"\usepackage{hyperref}",
        r"\usepackage{booktabs}",
        r"\usepackage{enumitem}",
        r"\usepackage{newunicodechar}",
        r"\usepackage[strings]{underscore}",  % FIX 2: Allows _ in normal text for source IDs
        "",
        r"% Fix layout warnings (overfull/underfull hbox)",
        r"\setlength{\emergencystretch}{3em}",
        r"\sloppy",
        "",
        r"% FIX 3: Compatibility layer for math commands used outside math mode",
        r"% If the LLM forgets $ $ around \in or \nabla, this saves the compilation.",
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
        r"% Safety net for Unicode symbols that slip past Python",
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
        body,
        "",
        r"\begin{thebibliography}{99}",
        refs_text,
        r"\end{thebibliography}",
        "",
        r"\end{document}",
    ]
    return "\n".join(doc_lines)
