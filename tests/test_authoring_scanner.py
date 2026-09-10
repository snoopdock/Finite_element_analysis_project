import pytest

from core.authoring_scanner import MathRegion, TextRegion, scan_authoring_text


def test_scanner_preserves_plain_text():
    assert scan_authoring_text("hello world") == [TextRegion("hello world")]


def test_scanner_recognizes_inline_math_as_opaque_region():
    assert scan_authoring_text("force $F=ma$ is fundamental") == [
        TextRegion("force "),
        MathRegion("$F=ma$", "$"),
        TextRegion(" is fundamental"),
    ]


def test_scanner_recognizes_display_math_variants():
    assert scan_authoring_text("a $$F=ma$$ b") == [
        TextRegion("a "),
        MathRegion("$$F=ma$$", "$$"),
        TextRegion(" b"),
    ]
    assert scan_authoring_text(r"a \[F=ma\] b") == [
        TextRegion("a "),
        MathRegion(r"\[F=ma\]", r"\["),
        TextRegion(" b"),
    ]


def test_escaped_dollar_remains_text():
    assert scan_authoring_text(r"cost is \$10") == [TextRegion(r"cost is \$10")]


@pytest.mark.parametrize("text", ["cost is $10", "before $$F=ma", r"before \[F=ma"])
def test_unmatched_math_delimiter_remains_text(text):
    assert scan_authoring_text(text) == [TextRegion(text)]


def test_markers_outside_math_remain_in_text_region():
    assert scan_authoring_text("supported [[CITE:source-1]].") == [
        TextRegion("supported [[CITE:source-1]].")
    ]


def test_markers_inside_math_are_opaque():
    text = "$[[CITE:source-1]]$"
    assert scan_authoring_text(text) == [MathRegion(text, "$")]


def test_legacy_square_bracket_citation_is_not_scanner_syntax():
    text = "supported [source-1]."
    assert scan_authoring_text(text) == [TextRegion(text)]


def test_adjacent_inline_math_regions_are_distinct():
    assert scan_authoring_text("$x$$y$") == [
        MathRegion("$x$", "$"),
        MathRegion("$y$", "$"),
    ]


def test_scanner_does_not_normalize_math_contents():
    text = r"before $  x  +  y  $ after"
    assert scan_authoring_text(text) == [
        TextRegion("before "),
        MathRegion(r"$  x  +  y  $", "$"),
        TextRegion(" after"),
    ]


def test_escaped_dollar_inside_math_does_not_close_region():
    text = r"$price = \$10$"
    assert scan_authoring_text(text) == [MathRegion(text, "$")]


def test_non_string_input_is_rejected():
    with pytest.raises(TypeError):
        scan_authoring_text(None)
