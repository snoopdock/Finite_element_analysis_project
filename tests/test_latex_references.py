"""Contract tests for LaTeX bibliography and provenance formatting."""

from processing.latex_ir import ReferenceModel
from processing.latex_references import (
    format_bibliography,
    format_bibliography_reference,
    format_provenance_row,
    format_provenance_table,
    format_retrieval_timestamp,
    format_source_type,
)


def _reference(**overrides):
    values = {
        "source_id": "source-1",
        "title": "Reference & Title",
        "url": "https://example.com/a&b#section",
        "source_type": "research.article",
        "retrieved_at": "2026-09-05T10:00:00Z",
        "citation_key": "ref1",
    }
    values.update(overrides)
    return ReferenceModel(**values)


def test_bibliography_uses_normalized_citation_key_and_escaped_metadata():
    rendered = format_bibliography_reference(_reference())

    assert r"\bibitem{ref1}" in rendered
    assert r"Reference \& Title" in rendered
    assert r"[Article]" in rendered
    assert r"https://example.com/a\&b\#section" in rendered


def test_bibliography_has_explicit_empty_source_fallback():
    assert format_bibliography([]) == r"  \bibitem{none} No sources retrieved."


def test_source_type_removes_internal_research_prefix_only_for_display():
    assert format_source_type("research.article") == "Article"
    assert format_source_type("misc") == "Misc"


def test_retrieval_timestamp_normalizes_iso_utc_value():
    assert format_retrieval_timestamp("2026-09-05T10:00:00Z") == "2026-09-05 10:00 UTC"


def test_retrieval_timestamp_preserves_unparseable_value():
    assert format_retrieval_timestamp("not-a-timestamp") == "not-a-timestamp"


def test_provenance_truncates_source_title_before_latex_escaping():
    title = "A" * 59 + "&" + "B" * 20
    rendered = format_provenance_row(0, _reference(title=title))

    assert r"A" * 1
    assert r"A" * 59 + r"\&" in rendered
    assert "B" not in rendered


def test_provenance_table_has_explicit_empty_source_fallback():
    assert format_provenance_table([]) == "No sources."


def test_provenance_table_preserves_reference_order():
    references = [
        _reference(source_id="source-1", citation_key="ref1", title="First"),
        _reference(source_id="source-2", citation_key="ref2", title="Second"),
    ]

    rendered = format_provenance_table(references)

    assert rendered.index("First") < rendered.index("Second")
    assert "source-1" in rendered
    assert "source-2" in rendered
