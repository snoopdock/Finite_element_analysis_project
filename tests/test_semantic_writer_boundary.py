import pytest

from writing.semantic_writer_boundary import (
    SEMANTIC_SECTION_KEY,
    attach_semantic_section,
    get_semantic_section,
)


SECTION_ID = "550e8400-e29b-41d4-a716-446655440000"


def test_attach_semantic_section_does_not_mutate_legacy_writer_output():
    section = {
        "section_id": SECTION_ID,
        "title": "Background",
        "content": "The relation is $u=x^2$. [source-1]",
        "key_equations": ["u=x^2"],
        "citations_used": ["source-1"],
        "parent_section_ids": [],
    }

    projected = attach_semantic_section(section)

    assert SEMANTIC_SECTION_KEY not in section
    assert projected["content"] == section["content"]
    assert projected["key_equations"] == ["u=x^2"]
    assert projected[SEMANTIC_SECTION_KEY]["section_id"] == SECTION_ID
    assert projected[SEMANTIC_SECTION_KEY]["children"][0]["type"] == "paragraph"
    assert projected[SEMANTIC_SECTION_KEY]["children"][0]["inline_content"][0]["text"] == section["content"]


def test_attach_semantic_section_uses_strict_marker_resolution():
    section = {
        "section_id": SECTION_ID,
        "title": "Weak Form",
        "content": "Supported [[CITE:source-1]]. [[EQ:eq-1]]",
    }

    projected = attach_semantic_section(
        section,
        equation_ids={"eq-1"},
        source_ids={"source-1"},
        target_ids=set(),
    )

    children = projected[SEMANTIC_SECTION_KEY]["children"]
    assert children[0]["type"] == "paragraph"
    assert children[0]["inline_content"][1]["type"] == "citation_occurrence"
    assert children[1]["type"] == "equation_occurrence"
    assert children[1]["equation_id"] == "eq-1"


def test_unknown_marker_reference_is_rejected():
    with pytest.raises(ValueError, match="Unknown equation_id"):
        attach_semantic_section(
            {
                "section_id": SECTION_ID,
                "title": "Invalid",
                "content": "[[EQ:eq-missing]]",
            },
            equation_ids={"eq-known"},
            source_ids=set(),
            target_ids=set(),
        )


def test_get_semantic_section_returns_only_attached_projection():
    section = {"section_id": SECTION_ID, "title": "Plain", "content": "text"}
    assert get_semantic_section(section) is None

    projected = attach_semantic_section(section)
    assert get_semantic_section(projected) == projected[SEMANTIC_SECTION_KEY]


def test_input_section_is_deep_copied():
    section = {
        "section_id": SECTION_ID,
        "title": "Copy",
        "content": "text",
        "nested": {"items": ["a"]},
    }

    projected = attach_semantic_section(section)
    projected["nested"]["items"].append("b")

    assert section["nested"]["items"] == ["a"]
