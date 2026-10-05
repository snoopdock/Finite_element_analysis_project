from processing.latex_builder import build_latex_document_from_model
from processing.latex_ir import (
    DocumentModel,
    IRMathSpan,
    IRTextSpan,
    ParagraphBlock,
    SectionModel,
)
from processing.latex_renderer import render_body
from utils.latex import normalize_math_expression


def _document(*items):
    return DocumentModel(
        topic="FEM",
        objective="Study L∞ stability.",
        sections=(
            SectionModel(
                title="Stability",
                section_id="11111111-1111-4111-8111-111111111111",
                label="sec:11111111-1111-4111-8111-111111111111",
                blocks=(ParagraphBlock(tuple(items)),),
            ),
        ),
    )


def test_typed_math_normalizes_unicode_infinity_to_latex_command():
    assert normalize_math_expression("L∞") == r"L\infty"
    body = render_body(_document(IRMathSpan("L∞")))
    assert r"\(L\infty\)" in body
    assert "∞" not in body


def test_plain_text_infinity_is_rendered_contextually_without_global_unicode_hook():
    tex = build_latex_document_from_model(
        {"knowledge_graph": {}},
        _document(IRTextSpan("The L∞ estimate is bounded.")),
    )
    assert r"\newunicodechar" not in tex
    assert r"\usepackage{newunicodechar}" not in tex
    assert r"The L\ensuremath{\infty} estimate is bounded." in tex
    assert "∞" not in tex


def test_unicode_math_normalization_does_not_rewrite_plain_ascii_latex():
    expression = r"L^{\infty}(\Omega)"
    assert normalize_math_expression(expression) == expression
