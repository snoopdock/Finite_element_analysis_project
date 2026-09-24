from pathlib import Path

from processing.quality_report_cli import generate_quality_report


def test_cli_generates_report_file(tmp_path):
    output = tmp_path / "quality_report.json"

    generate_quality_report(
        str(output)
    )

    assert output.exists()


def test_cli_output_is_deterministic(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    generate_quality_report(str(first))
    generate_quality_report(str(second))

    assert first.read_text() == second.read_text()
