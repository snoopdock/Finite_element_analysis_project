from pathlib import Path

from core.document_pipeline_integration import persist_pipeline_document


def test_persist_pipeline_document_writes_semantic_snapshot_without_replacing_sections(tmp_path: Path):
    sections = [
        {
            "section_id": "550e8400-e29b-41d4-a716-446655440000",
            "title": "Background",
            "content": "The relation is $u=x^2$. [source-1]",
            "key_equations": ["u=x^2"],
            "citations_used": ["source-1"],
            "parent_section_ids": [],
        }
    ]
    state = {"sections": sections}
    paths = {"document": tmp_path / "document.json"}

    result = persist_pipeline_document(state, paths)

    assert result == paths["document"]
    assert state["sections"] == sections
    assert paths["document"].exists()

    import json

    payload = json.loads(paths["document"].read_text(encoding="utf-8"))
    assert payload["type"] == "document"
    assert payload["children"][0]["section_id"] == sections[0]["section_id"]
    assert payload["children"][0]["children"][0]["type"] == "paragraph"
    assert payload["children"][0]["children"][0]["inline_content"][0]["text"] == sections[0]["content"]


def test_persist_pipeline_document_requires_document_path():
    try:
        persist_pipeline_document({"sections": []}, {})
    except ValueError as exc:
        assert "'document' path" in str(exc)
    else:
        raise AssertionError("Expected missing document path to fail")
