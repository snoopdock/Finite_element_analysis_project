import pytest

from core.document_model import (
    CitationOccurrence,
    EquationOccurrence,
    Paragraph,
)
from writing.section_document_adapter import (
    document_section_to_legacy,
    legacy_section_to_document_section,
    legacy_sections_to_document,
)


SECTION_ID = "550e8400-e29b-41d4-a716-446655440000"


def test_legacy_section_becomes_opaque_prose_without_semantic_inference():
    section = {
        "section_id": SECTION_ID,
        "title": "Background",
        "content": "The relation is $u=x^2$. [source-1]",
        "key_equations": ["u=x^2"],
        "citations_used": ["source-1"],
        "parent_section_ids": ["parent-1"],
        "status": "complete",
        "generated_from": "writer",
        "subsection_index": 2,
    }

    document = legacy_sections_to_document([section], document_id="doc-1")
    converted = document.children[0]

    assert document.document_id == "doc-1"
    assert converted.section_id == SECTION_ID
    assert converted.parent_section_ids == ["parent-1"]
    assert converted.status == "complete"
    assert converted.generated_from == "writer"
    assert converted.subsection_index == 2
    assert len(converted.children) == 1
    assert isinstance(converted.children[0], Paragraph)
    assert converted.children[0].inline_content[0].text == section["content"]
    assert not any(
        isinstance(node, CitationOccurrence)
        for node in converted.children[0].inline_content
    )
    assert not any(
        isinstance(child, EquationOccurrence)
        for child in converted.children
    )


def test_semantic_markers_use_strict_assembly_when_present():
    section = legacy_section_to_document_section(
        {
            "section_id": SECTION_ID,
            "title": "Weak Form",
            "content": "Supported [[CITE:source-1]]. [[EQ:eq-1]]",
            "parent_section_ids": ["parent-1"],
        },
        equation_ids={"eq-1"},
        source_ids={"source-1"},
        target_ids=set(),
    )

    assert section.section_id == SECTION_ID
    assert isinstance(section.children[0], Paragraph)
    assert isinstance(section.children[1], EquationOccurrence)
    assert isinstance(section.children[0].inline_content[1], CitationOccurrence)
    assert section.children[1].equation_id == "eq-1"


def test_semantic_projection_preserves_order_and_legacy_derived_metadata():
    section = legacy_section_to_document_section(
        {
            "section_id": SECTION_ID,
            "title": "Results",
            "content": (
                "First [[CITE:s1]]. [[EQ:eq-a]] "
                "Then [[CITE:s2]]. [[EQ:eq-b]]"
            ),
        },
        equation_ids={"eq-a", "eq-b"},
        source_ids={"s1", "s2"},
        target_ids=set(),
    )

    projected = document_section_to_legacy(section)

    assert projected["section_id"] == SECTION_ID
    assert projected["title"] == "Results"
    assert projected["key_equations"] == ["eq-a", "eq-b"]
    assert projected["citations_used"] == ["s1", "s2"]
    assert "[[CITE:s1]]" in projected["content"]
    assert "[[EQ:eq-a]]" in projected["content"]
    assert projected["content"].index("[[CITE:s1]]") < projected["content"].index("[[EQ:eq-a]]")
    assert projected["content"].index("[[EQ:eq-a]]") < projected["content"].index("[[CITE:s2]]")
    assert projected["content"].index("[[CITE:s2]]") < projected["content"].index("[[EQ:eq-b]]")


def test_unknown_semantic_reference_is_not_silently_substituted():
    with pytest.raises(ValueError, match="Unknown equation_id"):
        legacy_section_to_document_section(
            {
                "section_id": SECTION_ID,
                "title": "Invalid",
                "content": "[[EQ:eq-missing]]",
            },
            equation_ids={"eq-known"},
            source_ids=set(),
            target_ids=set(),
        )
