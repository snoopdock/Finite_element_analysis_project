"""Contract tests for the LaTeX document builder boundary."""

from processing.latex_builder import build_latex_document


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

    assert r"\cite{ref1}" in tex
    assert r"\bibitem{ref1}" in tex
    assert "paper-with-custom-id" in tex
    assert "Reference \\& Title" in tex
    assert "[Article]" in tex
    assert "2026-09-05 10:00 UTC" in tex
