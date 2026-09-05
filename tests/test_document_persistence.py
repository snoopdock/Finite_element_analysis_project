import json

import pytest

from core.document_model import Document, Paragraph
from core.document_persistence import (
    DocumentPersistenceError,
    build_document_from_legacy_sections,
    load_document,
    save_document,
)


SECTION_ID = "550e8400-e29b-41d4-a716-446655440000"


def test_build_document_from_legacy_sections_preserves_section_identity(tmp_path):
    document = build_document_from_legacy_sections(
        [
            {
                "section_id": SECTION_ID,
                "title": "Introduction",
                "content": "Free-form scientific prose.",
                "parent_section_ids": [],
            }
        ],
        document_id="doc-1",
    )

    assert isinstance(document, Document)
    assert document.document_id == "doc-1"
    assert document.children[0].section_id == SECTION_ID
    assert isinstance(document.children[0].children[0], Paragraph)


def test_save_and_load_preserves_serialized_document(tmp_path):
    document = build_document_from_legacy_sections(
        [
            {
                "section_id": SECTION_ID,
                "title": "Introduction",
                "content": "Free-form scientific prose.",
            }
        ],
        document_id="doc-1",
    )
    path = tmp_path / "document.json"

    save_document(document, path)
    loaded = load_document(path)

    assert loaded == document.to_dict()
    assert json.loads(path.read_text(encoding="utf-8")) == document.to_dict()


def test_load_missing_document_returns_none(tmp_path):
    assert load_document(tmp_path / "missing.json") is None


def test_load_rejects_non_object_json(tmp_path):
    path = tmp_path / "document.json"
    path.write_text("[]\n", encoding="utf-8")

    with pytest.raises(DocumentPersistenceError, match="must be a JSON object"):
        load_document(path)
