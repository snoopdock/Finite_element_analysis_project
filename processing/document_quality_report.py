from dataclasses import dataclass, field


@dataclass
class QualityIssue:
    code: str
    message: str
    severity: str = "warning"


@dataclass
class DocumentQualityReport:
    issues: list[QualityIssue] = field(default_factory=list)

    @property
    def valid(self):
        return not any(
            issue.severity == "error"
            for issue in self.issues
        )

    def add(self, code, message, severity="warning"):
        self.issues.append(
            QualityIssue(code, message, severity)
        )
