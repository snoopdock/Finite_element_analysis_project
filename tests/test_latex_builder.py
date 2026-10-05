"""Contract tests for the LaTeX document builder boundary."""

from processing.latex_builder import build_latex_document
from processing.latex_ir import citation_key_for_source_id


def test_builder_uses_normalized_reference_identity_for_bibliography_and_citations():
    tex = build_latex_document(
        {"topic": "Builder Test", "objective": "Verify reference identity", "knowledge_graph": {}},
        [
            {
                "title": "Evidence",
                "blocks": [
                    {"type": "text", "text": "A claim."},
                    {"type": "citation", "source_ids": ["paper-with-custom-id"]},
                ],
            }
        ],
        [
            {
                "source_id": "paper-with-custom-id",
                "title": "Reference & Title",
                "url": "https://example.com/a&b",
                "retriever_module": "research.article",
                "retrieved_at": "2026-09-05T10:00:00Z",
            }
        ],
    )

    key = citation_key_for_source_id("paper-with-custom-id")
    assert rf"\cite{{{key}}}" in tex
    assert rf"\bibitem{{{key}}}" in tex
    assert "paper-with-custom-id" in tex
    assert "Reference \\& Title" in tex
    assert "[Article]" in tex
    assert "2026-09-05 10:00 UTC" in tex


def test_builder_uses_ragged_right_provenance_columns():
    tex = build_latex_document(
        {"topic": "Builder Test", "objective": "Layout", "knowledge_graph": {}},
        [{"title": "Text", "blocks": [{"type": "text", "text": "Body"}]}],
        [],
    )

    assert r">{\raggedright\arraybackslash}p{3.1cm}" in tex
    assert r">{\raggedright\arraybackslash}p{5.7cm}" in tex


def test_builder_uses_ragged_right_bibliography_for_long_urls():
    tex = build_latex_document(
        {"topic": "Builder Test", "objective": "Bibliography layout", "knowledge_graph": {}},
        [{"title": "Text", "blocks": [
            {"type": "text", "text": "Body"},
            {"type": "citation", "source_ids": ["s2_0fb362f2f8848d66b6db1312e6826c995530007f"]},
        ]}],
        [{
            "source_id": "s2_0fb362f2f8848d66b6db1312e6826c995530007f",
            "title": "A $C^0$-continuous method",
            "url": "https://www.semanticscholar.org/paper/0fb362f2f8848d66b6db1312e6826c995530007f",
            "retriever_module": "research.semantic_scholar",
            "retrieved_at": "2026-10-03T19:48:00Z",
        }],
    )

    assert r"\begin{thebibliography}{99}" + "\n" + r"\raggedright" in tex
    assert r"\(C^0\)" in tex
    assert r"0fb362f2\allowbreak{}f8848d66" in tex


def test_builder_bibliography_contains_only_semantically_cited_sources_but_provenance_keeps_all():
    tex = build_latex_document(
        {"topic": "FEM", "objective": "Citation projection", "knowledge_graph": {}},
        [{"title": "Evidence", "blocks": [
            {"type": "text", "text": "Supported."},
            {"type": "citation", "source_ids": ["used_source"]},
        ]}],
        [
            {"source_id": "unused_source", "title": "Unused", "retriever_module": "research.article"},
            {"source_id": "used_source", "title": "Used", "retriever_module": "research.article"},
        ],
    )

    assert "\\bibitem{src:used_source-" in tex
    assert "\\bibitem{src:unused_source-" not in tex
    assert r"\nolinkurl{used_source}" in tex
    assert r"\nolinkurl{unused_source}" in tex
    assert r"\date{}" in tex
    assert r"\date{\today}" not in tex


def test_bibliography_order_follows_first_semantic_citation_not_evidence_order():
    state = {"topic": "FEM", "objective": "Citation ordering", "knowledge_graph": {}}
    sections = [{"title": "Evidence", "blocks": [
        {"type": "citation", "source_ids": ["second_source"]},
        {"type": "text", "text": " then "},
        {"type": "citation", "source_ids": ["first_source"]},
    ]}]
    evidence = [
        {"source_id": "first_source", "title": "First", "retriever_module": "research.article"},
        {"source_id": "second_source", "title": "Second", "retriever_module": "research.article"},
    ]
    tex = build_latex_document(state, sections, evidence)
    assert tex.index("\\bibitem{src:second_source-") < tex.index("\\bibitem{src:first_source-")
