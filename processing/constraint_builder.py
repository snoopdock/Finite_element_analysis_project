from .generation_constraint import GenerationConstraint


def build_constraints(feedback_rules):
    constraints = []

    for rule in feedback_rules:
        constraints.append(
            GenerationConstraint(
                category=rule.issue_category,
                instruction=rule.recommendation,
                priority=rule.priority,
            )
        )

    return constraints
