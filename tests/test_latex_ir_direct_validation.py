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
    validate_document_model,
)


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
