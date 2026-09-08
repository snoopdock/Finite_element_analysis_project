"""Contract tests for the semantic LaTeX document boundary."""

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
    build_document_model,
    normalize_sections,
    validate_document_model,
)
from processing.latex_renderer import render_block, render_body, render_section


def test_legacy_content_is_explicitly_marked():
    sections = normalize_sections(
        [{"title": "Introduction", "blocks": [{"type": "legacy_latex", "source": r"A & B"}]}]
    )

    assert len(sections) == 1
    assert isinstance(sections[0].blocks[0], LegacyLatexBlock)
    assert sections[0].blocks[0].source == r"A & B"


def test_implicit_content_is_rejected_at_the_boundary():
    with pytest.raises(DocumentModelError, match="unsupported fields"):
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


def test_unknown_citation_source_ids_fail_before_rendering():
    with pytest.raises(DocumentModelError, match="unknown source_id"):
        build_document_model(
            {},
            [
                {
                    "title": "Evidence",
                    "blocks": [
                        {"type": "citation", "source_ids": ["missing"]},
                    ],
                }
            ],
            [{"source_id": "known", "title": "Known"}],
        )


def test_empty_reference_source_ids_fail_at_the_boundary():
    with pytest.raises(DocumentModelError, match="source_id must not be empty"):
        build_document_model({}, [], [{"source_id": "", "title": "Untitled"}])


def test_direct_document_models_can_be_validated_before_rendering():
    document = DocumentModel(
        topic="Test",
        objective="Objective",
        sections=(
            SectionModel(title="Evidence", blocks=(CitationBlock(("missing",)),)),
        ),
        references=(
            ReferenceModel(source_id="known", title="Known", citation_key="ref1"),
        ),
    )

    with pytest.raises(DocumentModelError, match="unknown source_id"):
        validate_document_model(document)


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


def test_direct_citation_rendering_rejects_unknown_source_ids():
    with pytest.raises(DocumentModelError, match="unknown source_id"):
        render_block(CitationBlock(("missing",)), {"known": "ref1"})


def test_direct_citation_rendering_requires_reference_mapping():
    with pytest.raises(DocumentModelError, match="without a reference-number mapping"):
        render_block(CitationBlock(("known",)), None)


def test_section_rendering_preserves_block_order_and_citation_mapping():
    section = SectionModel(
        title="Evidence & Results",
        blocks=(
            TextBlock("First claim"),
            CitationBlock(("source",)),
            MathBlock(r"u = K^{-1}f"),
            TextBlock("Final claim"),
        ),
    )

    rendered = render_section(section, {"source": "ref7"})

    assert rendered.index("First claim") < rendered.index(r"\\cite{ref7}")
    assert rendered.index(r"\\cite{ref7}") < rendered.index(r"\\[u = K^{-1}f\\]")
    assert rendered.index(r"\\[u = K^{-1}f\\]") < rendered.index("Final claim")
    assert rendered.startswith(r"\\section{Evidence \& Results}")
