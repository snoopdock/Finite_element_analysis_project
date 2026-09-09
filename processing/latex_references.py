"""Reference formatting for LaTeX bibliography and provenance output.

This module owns presentation-only formatting of normalized ReferenceModel
instances. Citation identity remains authoritative in ReferenceModel.
"""

from datetime import datetime

from utils.latex import escape_latex


def format_retrieval_timestamp(retrieved_at):
    """Return a stable human-readable UTC timestamp when possible."""
    if retrieved_at == "N/A":
        return retrieved_at
    try:
        dt = datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError, AttributeError):
        return retrieved_at


def format_source_type(source_type):
    """Format an internal source type for publication display."""
    return escape_latex(source_type.replace("research.", "").title())


def format_bibliography_reference(reference):
    """Format one normalized reference as a LaTeX bibliography item."""
    title = escape_latex(reference.title)
    url = (
        reference.url.replace("%", r"\%")
        .replace("&", r"\&")
        .replace("#", r"\#")
    )
    return (
        f"  \\bibitem{{{reference.citation_key}}} \\textit{{{title}}}. "
        f"[{format_source_type(reference.source_type)}] "
        f"Available at: \\url{{{url}}}"
    )


def format_bibliography(references):
    """Format all normalized references, including the empty-source fallback."""
    items = [format_bibliography_reference(reference) for reference in references]
    return "\n".join(items) if items else "  \\bibitem{none} No sources retrieved."


def format_provenance_row(index, reference, title_limit=60):
    """Format one provenance table row.

    Truncation is applied to the source title before LaTeX escaping so the limit
    refers to source characters rather than rendered escape sequences.
    """
    source_id = escape_latex(reference.source_id)
    title = escape_latex(reference.title[:title_limit])
    retrieved = escape_latex(format_retrieval_timestamp(reference.retrieved_at))
    return (
        f"  {index + 1} & \\texttt{{{source_id}}} & {title} & "
        f"{format_source_type(reference.source_type)} & {retrieved} \\\\"
    )


def format_provenance_table(references):
    """Format all normalized references as provenance rows."""
    rows = [format_provenance_row(index, reference) for index, reference in enumerate(references)]
    return "\n".join(rows) if rows else "No sources."
