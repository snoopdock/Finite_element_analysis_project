from processing.document_quality_checks import validate_sections

def test_duplicate_sections_are_detected():
    report = validate_sections(
        [
            {"id": "intro", "title": "Introduction"},
            {"id": "intro", "title": "Another Introduction"},
        ]
    )

    assert report.valid is False


def test_missing_title_is_detected():
    report = validate_sections(
        [
            {"id": "intro", "title": ""}
        ]
    )

    assert report.valid is False


def test_valid_sections_pass():
    report = validate_sections(
        [
            {"id": "intro", "title": "Introduction"}
        ]
    )

    assert report.valid is True
