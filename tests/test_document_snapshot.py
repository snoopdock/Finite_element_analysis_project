from pathlib import Path

from core.document_snapshot import build_document_snapshot, persist_document_snapshot


SECTION_ID = "550e8400-e29b-41d4-a716-446655440000"
PARENT_ID = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"


def test_build_document_snapshot_preserves_section_identity_and_opaque_content():
    sections = [
        {
            "section_id": SECTION_ID,
            "title": "Background",
            "content": "The relation is $u=x^2$. [source-1]",
            "key_equations": ["u=x^2"],
            "citations_used": ["source-1"],
            "parent_section_ids": [PARENT_ID],
            "status": "complete",
            "generated_from": "writer",
            "subsection_index": 2,
        }
    ]

    document = build_document_snapshot(
        sections,
        document_id="doc-1",
        metadata={"origin": "pipeline"},
    )

    assert document.document_id == "doc-1"
    assert document.metadata == {"origin": "pipeline"}
    assert len(document.children) == 1

    section = document.children[0]
    assert section.section_id == SECTION_ID
    assert section.parent_section_ids == [PARENT_ID]
    assert section.children[0].inline_content[0].text == sections[0]["content"]


def test_persist_document_snapshot_writes_semantic_json(tmp_path: Path):
    path = tmp_path / "document.json"
    sections = [
        {
            "section_id": SECTION_ID,
            "title": "Background",
            "content": "Plain prose.",
            "parent_section_ids": [PARENT_ID],
        }
    ]

    document = persist_document_snapshot(
        sections,
        path,
        document_id="doc-2",
    )

    assert path.exists()
    assert document.document_id == "doc-2"

    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["type"] == "document"
    assert payload["document_id"] == "doc-2"
    assert payload["children"][0]["section_id"] == SECTION_ID
    assert payload["children"][0]["children"][0]["type"] == "paragraph"


def test_snapshot_does_not_infer_legacy_equations_or_citations():
    sections = [
        {
            "section_id": SECTION_ID,
            "title": "Background",
            "content": "Equation $u=x^2$ and [source-1].",
            "key_equations": ["u=x^2"],
            "citations_used": ["source-1"],
        }
    ]

    document = build_document_snapshot(sections)
    section = document.children[0]

    assert section.children[0].type == "paragraph"
    assert len(section.children) == 1
    assert section.children[0].inline_content[0].text == sections[0]["content"]
