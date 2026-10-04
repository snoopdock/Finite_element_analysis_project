"""Contract tests for LaTeX bibliography and provenance formatting."""

from processing.latex_ir import ReferenceModel
from processing.latex_references import (
    format_bibliography,
    format_bibliography_reference,
    format_provenance_row,
    format_provenance_table,
    format_reference_title,
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


def test_provenance_preserves_full_source_title_and_makes_long_ids_breakable():
    title = "A" * 59 + "&" + "B" * 20
    rendered = format_provenance_row(
        0,
        _reference(
            source_id="wiki_finite_element_limit_analysis",
            title=title,
        ),
    )

    assert r"A" * 59 + r"\&" + "B" * 20 in rendered
    assert r"\nolinkurl{wiki_finite_element_limit_analysis}" in rendered


def test_provenance_table_has_explicit_empty_source_fallback():
    assert format_provenance_table([]) == r"\multicolumn{5}{l}{No sources.} \\"


def test_provenance_table_preserves_reference_order():
    references = [
        _reference(source_id="source-1", citation_key="ref1", title="First"),
        _reference(source_id="source-2", citation_key="ref2", title="Second"),
    ]

    rendered = format_provenance_table(references)

    assert rendered.index("First") < rendered.index("Second")
    assert "source-1" in rendered
    assert "source-2" in rendered


def test_long_semantic_scholar_source_id_has_breaks_inside_hex_tail():
    rendered = format_provenance_row(
        0,
        _reference(source_id="s2_0fb362f2f8848d66b6db1312e6826c995530007f"),
    )

    assert r"s2\_\allowbreak{}0fb362f2\allowbreak{}f8848d66" in rendered
    assert r"\allowbreak{}b6db1312\allowbreak{}e6826c99" in rendered


def test_reference_title_preserves_only_safe_simple_inline_math():
    assert format_reference_title("A $C^0$-continuous method") == r"A \(C^0\)-continuous method"
    assert format_reference_title("Norms $H^1$ and $L^2$") == r"Norms \(H^1\) and \(L^2\)"


def test_reference_title_does_not_pass_arbitrary_latex_through():
    rendered = format_reference_title(r"Unsafe $\input{secret}$ title")

    assert r"\input{secret}" not in rendered
    assert r"\textbackslash{}input\{secret\}" in rendered
