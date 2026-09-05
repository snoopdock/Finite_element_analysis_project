from processing import document_renderer


def test_render_document_delegates_to_legacy_builder(monkeypatch):
    calls = {}

    def fake_builder(state, sections, evidence):
        calls["args"] = (state, sections, evidence)
        return "rendered-document"

    monkeypatch.setattr(
        "processing.latex_builder.build_latex_document",
        fake_builder,
    )

    state = {"topic": "FEM"}
    sections = [{"title": "Introduction"}]
    evidence = [{"source_id": "source-1"}]

    result = document_renderer.render_document(
        state,
        sections,
        evidence,
    )

    assert result == "rendered-document"
    assert calls["args"] == (state, sections, evidence)
