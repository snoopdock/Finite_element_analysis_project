from processing.quality_report_builder import build_quality_report
from processing.document_quality_report import QualityIssue


def test_report_collects_quality_information():
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

    assert report.document_id == "doc1"
    assert len(report.errors) == 1
    assert report.status == "error"


def test_clean_report_is_valid():
    report = build_quality_report("doc1")

    assert report.status == "valid"


def test_warning_report():
    issue = QualityIssue(
        code="short_section",
        message="Section is short",
        severity="warning",
    )

    report = build_quality_report(
        "doc1",
        issues=[issue],
    )

    assert report.status == "warning"
