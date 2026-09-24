import json


def serialize_quality_report(report):
    data = {
        "document_id": report.document_id,
        "status": report.status,
        "errors": [
            {
                "code": issue.code,
                "message": issue.message,
                "severity": issue.severity,
            }
            for issue in report.errors
        ],
        "warnings": [
            {
                "code": issue.code,
                "message": issue.message,
                "severity": issue.severity,
            }
            for issue in report.warnings
        ],
        "constraints": list(report.constraints),
    }

    return json.dumps(
        data,
        indent=2,
        sort_keys=True,
    )
