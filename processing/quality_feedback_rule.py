from dataclasses import dataclass


@dataclass(frozen=True)
class QualityFeedbackRule:
    issue_category: str
    recommendation: str
    priority: str = "normal"
