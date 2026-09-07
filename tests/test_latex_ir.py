"""Contract tests for the semantic LaTeX document boundary."""

import pytest

from processing.latex_ir import (
    CitationBlock,
    DocumentModelError,
    LegacyLatexBlock,
    MathBlock,
    TextBlock,
    build_document_model,
    normalize_sections,
)
from processing.latex_renderer import render_body


def test_legacy_content_is_explicitly_marked():
    sections = normalize_sections(
        [{"title": "Introduction", "blocks": [{"type": "legacy_latex", "source": r"A & B"}]}]
    )

    assert len(sections) == 1
    assert isinstance(sections[0].blocks[0], LegacyLatexBlock)
    assert sections[0].blocks[0].source == r"A & B"


def test_implicit_content_is_rejected_at_the_boundary():
    with pytest.raises(DocumentModelError, match="content is not accepted"):
        normalize_sections([{"title": "Introduction", "content": r"A & B"}])


def test_structured_blocks_preserve_semantic_kinds():
    sections = normalize_sections(
        [
            {
                "title": "Method",
                "blocks": [
                    {"type": "text", "text": "Plain text"},
                    {"type": "math", "expression": r"u = K^{-1}f"},
                ],
            }
        ]
    )

    assert isinstance(sections[0].blocks[0], TextBlock)
    assert isinstance(sections[0].blocks[1], MathBlock)


def test_unknown_block_types_fail_at_the_boundary():
    with pytest.raises(DocumentModelError, match="unsupported block type"):
        normalize_sections(
            [{"title": "Invalid", "blocks": [{"type": "table", "rows": []}]}]
        )


def test_renderer_escapes_text_but_preserves_math_structure():
    document = build_document_model(
        {"topic": "Test", "objective": "Objective"},
        [
            {
                "title": "Section",
                "blocks": [
                    {"type": "text", "text": "A & B"},
                    {"type": "math", "expression": r"u = K^{-1}f"},
                ],
            }
        ],
        [],
    )

    rendered = render_body(document)

    assert r"A \& B" in rendered
    assert r"\[u = K^{-1}f\]" in rendered


def test_document_model_limits_references_to_renderer_contract():
    document = build_document_model(
        {},
        [],
        [
            {"source_id": "one", "title": "One"},
            {"source_id": "two", "title": "Two"},
        ],
    )

    assert [reference.source_id for reference in document.references] == ["one", "two"]


def test_citation_blocks_resolve_against_explicit_reference_keys():
    document = build_document_model(
        {},
        [
            {
                "title": "Evidence",
                "blocks": [
                    {"type": "text", "text": "Claim"},
                    {"type": "citation", "source_ids": ["one", "two"]},
                ],
            }
        ],
        [
            {"source_id": "one", "title": "One"},
            {"source_id": "two", "title": "Two"},
        ],
    )

    assert isinstance(document.sections[0].blocks[1], CitationBlock)
    assert [reference.citation_key for reference in document.references] == [
        "ref1",
        "ref2",
    ]
    assert r"\cite{ref1,ref2}" in render_body(document)


def test_duplicate_reference_source_ids_fail_at_the_boundary():
    with pytest.raises(DocumentModelError, match="duplicate source_id"):
        build_document_model(
            {},
            [],
            [
                {"source_id": "same", "title": "First"},
                {"source_id": "same", "title": "Second"},
            ],
        )
