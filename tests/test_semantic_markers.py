import pytest

from core.semantic_markers import (
    SemanticMarker,
    SemanticMarkerError,
    TextSegment,
    parse_authoring_text,
)


def test_parse_preserves_free_form_text_and_marker_order():
    text = (
        "The formulation is given by "
        "[[EQ:eq-1]]. It is supported by [[CITE:source-1]] "
        "and refers to [[REF:eq-occ-1]]."
    )

    segments = parse_authoring_text(text)

    assert segments == [
        TextSegment("The formulation is given by "),
        SemanticMarker("EQ", "eq-1"),
        TextSegment(". It is supported by "),
        SemanticMarker("CITE", "source-1"),
        TextSegment(" and refers to "),
        SemanticMarker("REF", "eq-occ-1"),
        TextSegment("."),
    ]


def test_repeated_markers_remain_distinct_in_order():
    segments = parse_authoring_text("[[EQ:eq-1]] ... [[EQ:eq-1]]")

    assert [segment.identifier for segment in segments if isinstance(segment, SemanticMarker)] == [
        "eq-1",
        "eq-1",
    ]


def test_new_equation_proposal_is_a_marker_not_authority():
    segments = parse_authoring_text("Derived result: [[NEW_EQ:proposal-1]].")

    assert segments[1] == SemanticMarker("NEW_EQ", "proposal-1")


def test_unknown_marker_type_is_rejected():
    with pytest.raises(SemanticMarkerError, match="Unknown semantic marker type"):
        parse_authoring_text("Use [[FIGURE:fig-1]] here.")


def test_empty_identifier_is_rejected():
    with pytest.raises(SemanticMarkerError, match="malformed semantic marker"):
        parse_authoring_text("Use [[EQ:]] here.")


def test_unterminated_marker_is_rejected():
    with pytest.raises(SemanticMarkerError, match="Unterminated semantic marker"):
        parse_authoring_text("Use [[EQ:eq-1 here.")


def test_non_string_authoring_output_is_rejected():
    with pytest.raises(SemanticMarkerError, match="must be a string"):
        parse_authoring_text(None)
