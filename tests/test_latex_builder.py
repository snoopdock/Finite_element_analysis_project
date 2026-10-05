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
        [{"title": "Text", "blocks": [{"type": "text", "text": "Body"}]}],
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
