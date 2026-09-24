import argparse
from pathlib import Path

from .quality_report_builder import build_quality_report
from .quality_report_serializer import serialize_quality_report


def generate_quality_report(output_path: str):
    report = build_quality_report(
        document_id="ci_run"
    )

    content = serialize_quality_report(report)

    path = Path(output_path)
    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    path.write_text(
        content,
        encoding="utf-8"
    )

    return path


def main():
    parser = argparse.ArgumentParser(
        description="Generate quality report artifact"
    )

    parser.add_argument(
        "--output",
        required=True
    )

    args = parser.parse_args()

    generate_quality_report(args.output)


if __name__ == "__main__":
    main()
