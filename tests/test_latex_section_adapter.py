from processing.latex_section_adapter import (
    adapt_section_to_latex_ir,
    adapt_sections_to_latex_ir,
)


def test_section_adapter_creates_blocks():
    section = {
        "title": "Introduction",
        "content": "Finite Element Method content.",
        "key_equations": ["K u = F"],
        "citations_used": ["source_1"],
    }

    result = adapt_section_to_latex_ir(section)

    assert result["title"] == "Introduction"
    assert len(result["blocks"]) == 3
    assert result["blocks"][0]["type"] == "text"
    assert result["blocks"][1]["type"] == "math"
    assert result["blocks"][2]["type"] == "citation"


def test_multiple_sections_are_adapted():
    sections = [
        {
            "title": "A",
            "content": "Text",
        },
        {
            "title": "B",
            "content": "Text",
        },
    ]

    result = adapt_sections_to_latex_ir(sections)

    assert len(result) == 2
    assert result[0]["title"] == "A"


def test_empty_optional_fields_are_allowed():
    result = adapt_section_to_latex_ir(
        {
            "title": "Minimal",
        }
    )

    assert result["title"] == "Minimal"
    assert result["blocks"] == []
