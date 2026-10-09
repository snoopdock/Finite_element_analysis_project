import pytest

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.evolution import IncrementalReverificationService, ReverificationReplayCatalog, SemanticGraphEvolutionService
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.analysis import SemanticContext
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.orchestration import builtin_profile_catalog
from audit_engine.semantic_audit.rules import DomainRuleExecutor, DomainRuleLoader
from audit_engine.semantic_audit.verification import GraphAttributeConstraintVerifier, VerificationService, VerifierRegistry


def make_graph(*, exp1_lifecycle="experimental", exp2_lifecycle="experimental", include_exp1=True, include_exp2=True):
    graph = SemanticGraph()
    graph.add_node(SemanticNode("prod", "Module", attributes={"lifecycle": "production"}))
    graph.add_node(SemanticNode("exp1", "Module", attributes={"lifecycle": exp1_lifecycle}))
    graph.add_node(SemanticNode("exp2", "Module", attributes={"lifecycle": exp2_lifecycle}))
    if include_exp1:
        graph.add_edge(SemanticEdge("prod", "exp1", "DEPENDS_ON", metadata={"source_id": "code:1"}))
    if include_exp2:
        graph.add_edge(SemanticEdge("prod", "exp2", "DEPENDS_ON", metadata={"source_id": "code:2"}))
    return graph


def build_transition(before_graph, after_graph, semantic_context, artifacts):
    evolution = SemanticGraphEvolutionService().compare(
        before_graph=before_graph,
        after_graph=after_graph,
        before_context=semantic_context,
        artifacts=artifacts,
    )
    assessment = IncrementalReverificationService().assess(
        evolution=evolution,
        artifacts=artifacts,
    )
    return evolution, assessment


@pytest.fixture
def semantic_context():
    return SemanticContext(relationship_vocabulary_version="repo-relations/v1")


@pytest.fixture
def verification_stack():
    registry = VerifierRegistry()
    registry.register(GraphAttributeConstraintVerifier())
    return registry, VerificationService(registry), builtin_profile_catalog()


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
def two_receipt_chain(semantic_context, verification_stack, domain_rule):
    registry, service, profiles = verification_stack
    graph = make_graph()
    analysis = SemanticGraphAnalysisService(graph, semantic_context=semantic_context).analyze(
        GraphQuery("g332-domain", QueryType.DEPENDENCY, ["prod"], {"max_depth": 1})
    )
    execution = DomainRuleExecutor(service).execute(domain_rule, analysis, graph)
    assert len(execution.receipts) == 2
    assert len(execution.findings) == 2
    catalog = ReverificationReplayCatalog()
    catalog.add_domain_execution(analysis=analysis, rule=domain_rule, execution=execution)
    artifacts = [analysis, *execution.receipts, *execution.findings]
    return graph, analysis, execution, catalog, artifacts, registry, service, profiles
