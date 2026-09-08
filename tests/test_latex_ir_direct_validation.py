"""Regression tests for direct semantic IR validation."""

import pytest

from processing.latex_ir import (
    CitationBlock,
    DocumentModel,
    DocumentModelError,
    LegacyLatexBlock,
    MathBlock,
    ReferenceModel,
    SectionModel,
    TextBlock,
    normalize_references,
    normalize_sections,
    validate_document_model,
)
from processing.latex_renderer import render_body


def _document(section: SectionModel) -> DocumentModel:
    return DocumentModel(
        topic="Test",
        objective="Objective",
        sections=(section,),
        references=(ReferenceModel(source_id="known", title="Known", citation_key="ref1"),),
    )


def test_direct_model_rejects_non_tuple_blocks():
    document = _document(SectionModel(title="Section", blocks=[TextBlock("text")]))

    with pytest.raises(DocumentModelError, match="blocks must be a tuple"):
        validate_document_model(document)


def test_direct_model_rejects_non_string_text():
    document = _document(SectionModel(title="Section", blocks=(TextBlock(123),)))

    with pytest.raises(DocumentModelError, match="text must be a non-empty string"):
        validate_document_model(document)


def test_direct_model_rejects_non_string_math():
    document = _document(SectionModel(title="Section", blocks=(MathBlock(123),)))

    with pytest.raises(DocumentModelError, match="expression must be a non-empty string"):
        validate_document_model(document)


def test_direct_model_rejects_non_tuple_citation_ids():
    document = _document(SectionModel(title="Section", blocks=(CitationBlock(["known"]),)))

    with pytest.raises(DocumentModelError, match="source_ids must be a tuple"):
        validate_document_model(document)


def test_direct_model_rejects_non_string_legacy_source():
    document = _document(SectionModel(title="Section", blocks=(LegacyLatexBlock(123),)))

    with pytest.raises(DocumentModelError, match="source must be a non-empty string"):
        validate_document_model(document)


def test_direct_model_rejects_non_string_reference_fields():
    document = DocumentModel(
        topic="Test",
        objective="Objective",
        sections=(),
        references=(ReferenceModel(source_id="known", title=123, citation_key="ref1"),),
    )

    with pytest.raises(DocumentModelError, match="reference 0.title must be a string"):
        validate_document_model(document)


def test_renderer_rejects_non_string_section_titles_before_rendering():
    document = _document(SectionModel(title=123, blocks=(TextBlock("text"),)))

    with pytest.raises(DocumentModelError, match="section 0.title must be a string"):
        render_body(document)


def test_renderer_rejects_invalid_citation_containers_before_rendering():
    document = _document(SectionModel(title="Section", blocks=(CitationBlock(["known"]),)))

    with pytest.raises(DocumentModelError, match="source_ids must be a tuple"):
        render_body(document)


def test_normalize_references_rejects_unsupported_fields():
    evidence = [{"source_id": "known", "title": "Known", "unexpected": "value"}]

    with pytest.raises(DocumentModelError, match="evidence 0 contains unsupported fields: unexpected"):
        normalize_references(evidence)


def test_normalize_sections_rejects_non_sequence_input():
    with pytest.raises(DocumentModelError, match="sections must be a sequence"):
        normalize_sections({"title": "Section", "blocks": []})


def test_normalize_references_rejects_non_sequence_input():
    with pytest.raises(DocumentModelError, match="evidence must be a sequence"):
        normalize_references({"source_id": "known"})


def test_normalize_sections_rejects_non_mapping_item():
    with pytest.raises(DocumentModelError, match="section 0 must be a mapping"):
        normalize_sections(["invalid"])


def test_normalize_references_rejects_non_mapping_item():
    with pytest.raises(DocumentModelError, match="evidence 0 must be a mapping"):
        normalize_references(["invalid"])


def test_normalize_sections_rejects_unsupported_block_type():
    sections = [{"title": "Section", "blocks": [{"type": "unsupported"}]}]

    with pytest.raises(DocumentModelError, match="unsupported block type 'unsupported'"):
        normalize_sections(sections)


def test_normalize_sections_rejects_unsupported_fields():
    sections = [{"title": "Section", "blocks": [], "unexpected": "value"}]

    with pytest.raises(DocumentModelError, match="section 0 contains unsupported fields: unexpected"):
        normalize_sections(sections)
