"""Reference formatting for LaTeX bibliography and provenance output.

This module owns presentation-only formatting of normalized ReferenceModel
instances. Citation identity remains authoritative in ReferenceModel.
"""

from datetime import datetime
import re

from utils.latex import escape_latex, escape_text


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


_SAFE_TITLE_MATH_RE = re.compile(r"^[A-Za-z0-9 +\-*/=<>^_().,]+$")
_TITLE_MATH_FRAGMENT_RE = re.compile(r"\$([^$]+)\$")


def format_reference_title(title):
    """Escape external title metadata while preserving a tiny safe math subset.

    Source titles are untrusted metadata, so arbitrary LaTeX is never passed
    through.  Only simple dollar-delimited ASCII math fragments without
    commands (for example ``$C^0$`` or ``$H^1$``) are promoted to inline
    math.  Everything else remains escaped plain text.
    """
    if not title:
        return ""

    rendered = []
    cursor = 0
    for match in _TITLE_MATH_FRAGMENT_RE.finditer(title):
        rendered.append(escape_text(title[cursor:match.start()]))
        fragment = match.group(1).strip()
        if fragment and _SAFE_TITLE_MATH_RE.fullmatch(fragment):
            rendered.append(r"\(" + fragment + r"\)")
        else:
            rendered.append(escape_text(match.group(0)))
        cursor = match.end()
    rendered.append(escape_text(title[cursor:]))
    return "".join(rendered)


def format_bibliography_reference(reference):
    """Format one normalized reference as a LaTeX bibliography item."""
    title = format_reference_title(reference.title)
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


def _format_breakable_source_id(source_id, *, chunk_size=8, long_run_threshold=16):
    """Format a source ID with safe discretionary break points when required.

    Normal identifiers keep the established ``\nolinkurl`` representation.
    If an identifier contains a long uninterrupted alphanumeric run (as in
    Semantic Scholar hashes), it is rendered as escaped monospace text with
    zero-width ``\allowbreak`` opportunities every ``chunk_size`` characters.
    No identifier content is interpreted as LaTeX.
    """
    source_id = str(source_id or "")
    if not source_id:
        return r"\texttt{N/A}"

    runs = re.findall(r"[A-Za-z0-9]+", source_id)
    if not any(len(run) > long_run_threshold for run in runs):
        return rf"\nolinkurl{{{source_id}}}"

    pieces = []
    run = []

    def flush_run():
        if not run:
            return
        text = "".join(run)
        for start in range(0, len(text), chunk_size):
            if start:
                pieces.append(r"\allowbreak{}")
            pieces.append(escape_text(text[start:start + chunk_size]))
        run.clear()

    for char in source_id:
        if char.isalnum():
            run.append(char)
            continue
        flush_run()
        pieces.append(escape_text(char))
        pieces.append(r"\allowbreak{}")
    flush_run()

    return r"\texttt{" + "".join(pieces) + "}"


def format_provenance_row(index, reference):
    """Format one provenance row without truncating source metadata."""
    source_id = _format_breakable_source_id(reference.source_id)
    title = format_reference_title(reference.title)
    retrieved = escape_latex(format_retrieval_timestamp(reference.retrieved_at))
    return (
        f"  {index + 1} & {source_id} & {title} & "
        f"{format_source_type(reference.source_type)} & {retrieved} \\\\"
    )


def format_provenance_table(references):
    """Format all normalized references as provenance rows."""
    rows = [format_provenance_row(index, reference) for index, reference in enumerate(references)]
    return "\n".join(rows) if rows else r"\multicolumn{5}{l}{No sources.} \\"
