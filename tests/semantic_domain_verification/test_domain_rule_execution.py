from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.rules import DomainRuleExecutor, DomainRuleLoader, RuleDisposition


def test_architecture_domain_rule_creates_only_experimental_dependency_finding(
    dependency_result, domain_graph, verification_service
):
    rule = DomainRuleLoader.from_yaml(
        "specs/rules/architecture/no_production_to_experimental_dependency.yaml"
    )
    execution = DomainRuleExecutor(verification_service).execute(
        rule, dependency_result, domain_graph
    )
    assert len(execution.obligations) == 2
    assert len(execution.findings) == 1
    assert execution.findings[0].rule_id == rule.policy.rule_id
    triggered = [e for e in execution.evaluations if e.disposition is RuleDisposition.TRIGGERED]
    assert len(triggered) == 1


def test_provenance_domain_rule_has_no_finding_when_sources_present(
    dependency_result, domain_graph, verification_service
):
    rule = DomainRuleLoader.from_yaml(
        "specs/rules/provenance/evidence_requires_source_identity.yaml"
    )
    execution = DomainRuleExecutor(verification_service).execute(
        rule, dependency_result, domain_graph
    )
    assert execution.reason == "executed"
    assert not execution.findings


def test_provenance_domain_rule_finds_missing_source(domain_graph, verification_service):
    domain_graph.edges[0].metadata.clear()
    result = SemanticGraphAnalysisService(domain_graph).analyze(
        GraphQuery("missing-prov", QueryType.DEPENDENCY, ["prod"], {"max_depth": 1})
    )
    rule = DomainRuleLoader.from_yaml(
        "specs/rules/provenance/evidence_requires_source_identity.yaml"
    )
    execution = DomainRuleExecutor(verification_service).execute(rule, result, domain_graph)
    assert len(execution.findings) == 1


def test_scientific_support_rule_no_finding_when_support_exists(
    claim_result, domain_graph, verification_service
):
    rule = DomainRuleLoader.from_yaml(
        "specs/rules/scientific/claim_requires_support_relationship.yaml"
    )
    execution = DomainRuleExecutor(verification_service).execute(rule, claim_result, domain_graph)
    assert len(execution.receipts) == 1
    assert not execution.findings


def test_scientific_support_rule_finds_graph_scoped_absence(verification_service):
    graph = SemanticGraph()
    graph.add_node(SemanticNode("claim:2", "ScientificClaim"))
    result = SemanticGraphAnalysisService(graph).analyze(
        GraphQuery("claim2", QueryType.STRUCTURAL, ["claim:2"], {"direction": "outgoing"})
    )
    rule = DomainRuleLoader.from_yaml(
        "specs/rules/scientific/claim_requires_support_relationship.yaml"
    )
    execution = DomainRuleExecutor(verification_service).execute(rule, result, graph)
    assert len(execution.findings) == 1
    assert "support relationship" in execution.findings[0].message


def test_domain_rule_context_mismatch_is_ineligible(
    dependency_result, domain_graph, verification_service
):
    payload = {
        "rule_id": "context.restricted",
        "version": "1",
        "domain": "architecture",
        "obligation_type": "graph_attribute_constraint",
        "verifier_id": "graph-attribute-constraint",
        "title": "Restricted",
        "finding_message": "Restricted",
        "required_semantic_context": {"relationship_vocabulary_version": "different/v1"},
    }
    rule = DomainRuleLoader.from_mapping(payload)
    execution = DomainRuleExecutor(verification_service).execute(
        rule, dependency_result, domain_graph
    )
    assert not execution.eligible
    assert execution.reason == "semantic_context_mismatch"


def test_domain_rule_selector_can_yield_no_targets(
    dependency_result, domain_graph, verification_service
):
    payload = {
        "rule_id": "no.targets",
        "version": "1",
        "domain": "architecture",
        "obligation_type": "graph_attribute_constraint",
        "verifier_id": "graph-attribute-constraint",
        "title": "No targets",
        "finding_message": "No targets",
        "selector": {"scope": "observation", "predicates": ["CALLS"]},
    }
    rule = DomainRuleLoader.from_mapping(payload)
    execution = DomainRuleExecutor(verification_service).execute(rule, dependency_result, domain_graph)
    assert execution.eligible
    assert execution.reason == "no_matching_targets"
    assert not execution.receipts
