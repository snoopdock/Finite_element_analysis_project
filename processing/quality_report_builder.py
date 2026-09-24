from .quality_report import QualityReport


def build_quality_report(
    document_id,
    issues=None,
    diagnostics=None,
    constraints=None,
):
    return QualityReport(
        document_id=document_id,
        issues=list(issues or []),
        diagnostics=list(diagnostics or []),
        constraints=list(constraints or []),
    )
