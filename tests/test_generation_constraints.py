from processing.constraint_builder import build_constraints
from processing.quality_feedback_rule import QualityFeedbackRule


def test_feedback_becomes_constraint():
    rules = [
        QualityFeedbackRule(
            issue_category="empty_content",
            recommendation="Add substantive content",
            priority="high",
        )
    ]

    constraints = build_constraints(rules)

    assert len(constraints) == 1
    assert constraints[0].priority == "high"


def test_constraint_conversion_is_deterministic():
    rules = [
        QualityFeedbackRule(
            issue_category="structure",
            recommendation="Improve structure",
        )
    ]

    assert build_constraints(rules) == build_constraints(rules)
