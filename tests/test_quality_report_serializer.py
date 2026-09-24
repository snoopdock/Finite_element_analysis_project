from processing.quality_report_serializer import serialize_quality_report
from processing.quality_report_builder import build_quality_report
from processing.document_quality_report import QualityIssue


def test_report_serialization_is_deterministic():
    issue = QualityIssue(
        code="missing_title",
        message="Missing title",
        severity="error",
    )

    report = build_quality_report(
        "doc1",
        issues=[issue],
        constraints=["add title"],
    )

    first = serialize_quality_report(report)
    second = serialize_quality_report(report)

    assert first == second


def test_serialized_report_contains_status():
    report = build_quality_report("doc1")

    output = serialize_quality_report(report)

    assert '"status": "valid"' in output


def test_serialized_report_contains_constraints():
    report = build_quality_report(
        "doc1",
        constraints=["expand section"],
    )

    output = serialize_quality_report(report)

    assert "expand section" in output
