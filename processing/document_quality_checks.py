from .document_quality_report import DocumentQualityReport


def validate_sections(sections):
    report = DocumentQualityReport()

    seen_ids = set()

    for section in sections:
        section_id = section.get("id")

        if not section_id:
            report.add(
                "MISSING_SECTION_ID",
                "Section has no identifier",
                "error"
            )
        elif section_id in seen_ids:
            report.add(
                "DUPLICATE_SECTION_ID",
                f"Duplicate section id: {section_id}",
                "error"
            )

        seen_ids.add(section_id)

        if not section.get("title"):
            report.add(
                "MISSING_TITLE",
                "Section title is empty",
                "error"
            )

    return report
