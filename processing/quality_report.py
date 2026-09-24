from dataclasses import dataclass, field


@dataclass
class QualityReport:
    document_id: str
    issues: list = field(default_factory=list)
    diagnostics: list = field(default_factory=list)
    constraints: list = field(default_factory=list)

    @property
    def errors(self):
        return [
            item for item in self.issues
            if getattr(item, "severity", None) == "error"
        ]

    @property
    def warnings(self):
        return [
            item for item in self.issues
            if getattr(item, "severity", None) == "warning"
        ]

    @property
    def status(self):
        if self.errors:
            return "error"

        if self.warnings or self.diagnostics:
            return "warning"

        return "valid"
