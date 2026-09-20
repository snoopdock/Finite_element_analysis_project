from dataclasses import dataclass


@dataclass(frozen=True)
class ArtifactIssue:
    category: str
    severity: str
    message: str
    location: str = ""
