import pytest

from audit_engine.semantic_audit.evolution import ReverificationReplayCatalog
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.analysis import SemanticContext
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.rules import DomainRuleExecutor, DomainRuleLoader
from audit_engine.semantic_audit.verification import GraphAttributeConstraintVerifier, VerificationService, VerifierRegistry

from .helpers import make_graph


@pytest.fixture
def semantic_context():
    return SemanticContext(relationship_vocabulary_version="repo-relations/v1")


@pytest.fixture
def verification_service():
    registry = VerifierRegistry()
    registry.register(GraphAttributeConstraintVerifier())
    return VerificationService(registry)


@pytest.fixture
def domain_rule():
    return DomainRuleLoader.from_mapping({
        "rule_id": "architecture.no_production_to_experimental_dependency",
        "version": "1",
        "domain": "architecture",
        "obligation_type": "graph_attribute_constraint",
        "verifier_id": "graph-attribute-constraint",
        "title": "Production dependency reaches experimental module",
        "finding_message": "Production code depends on an experimental module.",
        "severity": "critical",
        "selector": {
            "scope": "observation",
            "predicates": ["DEPENDS_ON"],
            "source_entity_types": ["Module"],
            "target_entity_types": ["Module"],
        },
        "parameters": {
            "relation_types": ["DEPENDS_ON"],
            "source_attributes": {"lifecycle": "production"},
            "target_attributes": {"lifecycle": "experimental"},
        },
    })


@pytest.fixture
def audit_chain(semantic_context, verification_service, domain_rule):
    graph = make_graph()
    analysis = SemanticGraphAnalysisService(graph, semantic_context=semantic_context).analyze(
        GraphQuery("g322-domain", QueryType.DEPENDENCY, ["prod"], {"max_depth": 1})
    )
    execution = DomainRuleExecutor(verification_service).execute(domain_rule, analysis, graph)
    assert len(execution.receipts) == 1
    assert len(execution.findings) == 1
    catalog = ReverificationReplayCatalog()
    catalog.add_domain_execution(analysis=analysis, rule=domain_rule, execution=execution)
    artifacts = [analysis, *execution.receipts, *execution.findings]
    return graph, analysis, execution, catalog, artifacts
