"""Regression tests for document metadata validation."""

import pytest

from processing.latex_ir import DocumentModel, DocumentModelError, validate_document_model


@pytest.mark.parametrize("field", ["topic", "objective"])
def test_direct_document_model_rejects_non_string_metadata(field):
    values = {"topic": "Test", "objective": "Objective"}
    values[field] = 123
    document = DocumentModel(
        topic=values["topic"],
        objective=values["objective"],
        sections=(),
        references=(),
    )

    with pytest.raises(DocumentModelError, match="topic and objective must be strings"):
        validate_document_model(document)
