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
    display = source_type.replace("research.", "").replace("_", " ").title()
    return escape_latex(display)


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


def _format_breakable_source_id(source_id):
    """Format a source identifier with URL-style discretionary line breaks."""
    # ``\nolinkurl`` is presentation-only and handles underscores/long tokens
    # without creating a clickable link. Source IDs are pipeline-controlled
    # identifiers rather than arbitrary authorial LaTeX.
    return rf"\nolinkurl{{{source_id}}}"


def format_provenance_row(index, reference):
    """Format one provenance row without truncating source metadata."""
    source_id = _format_breakable_source_id(reference.source_id)
    title = escape_latex(reference.title)
    retrieved = escape_latex(format_retrieval_timestamp(reference.retrieved_at))
    return (
        f"  {index + 1} & {source_id} & {title} & "
        f"{format_source_type(reference.source_type)} & {retrieved} \\\\"
    )


def format_provenance_table(references):
    """Format all normalized references as provenance rows."""
    rows = [format_provenance_row(index, reference) for index, reference in enumerate(references)]
    return "\n".join(rows) if rows else "No sources."
