import pytest

from audit_engine.semantic_audit.rules import DomainRuleLoader, DomainRuleScope
from audit_engine.semantic_audit.verification import VerificationDecision


def base_rule():
    return {
        "rule_id": "architecture.example",
        "version": "1",
        "domain": "architecture",
        "obligation_type": "graph_attribute_constraint",
        "verifier_id": "graph-attribute-constraint",
        "title": "Example",
        "finding_message": "Example finding",
        "selector": {"scope": "observation", "predicates": ["DEPENDS_ON"]},
        "parameters": {"source_attributes": {"lifecycle": "production"}},
    }


def test_domain_rule_loader_maps_policy_and_verifier():
    rule = DomainRuleLoader.from_mapping(base_rule())
    assert rule.domain == "architecture"
    assert rule.verifier_id == "graph-attribute-constraint"
    assert rule.selector.scope is DomainRuleScope.OBSERVATION
    assert rule.policy.trigger_decision is VerificationDecision.CONFIRMED


def test_domain_rule_loader_rejects_unknown_top_level_field():
    payload = base_rule()
    payload["mystery"] = True
    with pytest.raises(ValueError, match="Unknown domain audit rule fields"):
        DomainRuleLoader.from_mapping(payload)


def test_domain_rule_loader_rejects_unknown_selector_field():
    payload = base_rule()
    payload["selector"]["unknown"] = True
    with pytest.raises(ValueError, match="Unknown selector fields"):
        DomainRuleLoader.from_mapping(payload)


def test_domain_rule_loader_loads_repository_example():
    rule = DomainRuleLoader.from_yaml(
        "specs/rules/architecture/no_production_to_experimental_dependency.yaml"
    )
    assert rule.policy.rule_id == "architecture.no_production_to_experimental_dependency"
