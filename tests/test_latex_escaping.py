"""Contract tests for context-specific LaTeX escaping."""

from processing.latex_renderer import render_block, render_section
from processing.latex_ir import LegacyLatexBlock, SectionModel, TextBlock
from utils.latex import escape_latex, escape_text, sanitize_latex_content


def test_escape_text_escapes_all_plain_text_special_characters():
    value = r"A & B # C % D $ E _ F { G } H ~ I ^ J \ K"

    assert escape_text(value) == (
        r"A \& B \# C \% D \$ E \_ F \{ G \} H "
        r"\textasciitilde{} I \textasciicircum{} J "
        r"\textbackslash{} K"
    )


def test_escape_latex_preserves_commands_but_escapes_text_specials():
    value = r"\textbf{A & B} and $10 _ percent%"

    assert escape_latex(value) == (
        r"\textbf{A \& B} and \$10 \_ percent\%"
    )


def test_semantic_text_block_does_not_create_math_from_dollar_signs():
    rendered = render_block(TextBlock("The price is $10."))

    assert rendered == r"The price is \$10."


def test_semantic_section_title_is_plain_text():
    section = SectionModel(
        title=r"Results $10 & 20%",
        blocks=(TextBlock("Content"),),
    )

    rendered = render_section(section)

    assert rendered.startswith(r"\section{Results \$10 \& 20\%}")


def test_legacy_latex_remains_explicitly_compatible():
    source = r"\textbf{A & B} and $x^2$"

    assert sanitize_latex_content(source) == r"\textbf{A \& B} and $x^2$"
    assert render_block(LegacyLatexBlock(source)) == r"\textbf{A \& B} and $x^2$"
