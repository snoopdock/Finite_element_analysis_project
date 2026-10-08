import pytest

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.analysis import VerificationStatus
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.verification import (
    VerificationAttempt,
    VerificationDecision,
    VerificationObligation,
    VerificationService,
    VerifierDescriptor,
    VerifierRegistry,
)


class CheapInconclusiveVerifier:
    descriptor = VerifierDescriptor("cheap-inconclusive", "1.0.0", ("observation_contract",))

    def verify(self, obligation, context):
        context.validate_obligation_binding(obligation)
        return VerificationAttempt.create(
            obligation_id=obligation.obligation_id,
            verifier_id=self.descriptor.verifier_id,
            verifier_version=self.descriptor.version,
            decision=VerificationDecision.INCONCLUSIVE,
            evidence_state=VerificationStatus.INCONCLUSIVE,
            evidence_ids=obligation.evidence_ids,
            details={"reason": "fixture_inconclusive"},
        )


class ExpensiveConfirmVerifier:
    descriptor = VerifierDescriptor("expensive-confirm", "1.0.0", ("observation_contract",))

    def verify(self, obligation, context):
        context.validate_obligation_binding(obligation)
        return VerificationAttempt.create(
            obligation_id=obligation.obligation_id,
            verifier_id=self.descriptor.verifier_id,
            verifier_version=self.descriptor.version,
            decision=VerificationDecision.CONFIRMED,
            evidence_state=VerificationStatus.VALIDATED,
            evidence_ids=obligation.evidence_ids,
            details={"fixture": "confirmed"},
        )


class CheapConfirmVerifier:
    descriptor = VerifierDescriptor("cheap-confirm", "1.0.0", ("observation_contract",))

    def verify(self, obligation, context):
        context.validate_obligation_binding(obligation)
        return VerificationAttempt.create(
            obligation_id=obligation.obligation_id,
            verifier_id=self.descriptor.verifier_id,
            verifier_version=self.descriptor.version,
            decision=VerificationDecision.CONFIRMED,
            evidence_state=VerificationStatus.VALIDATED,
            evidence_ids=obligation.evidence_ids,
        )


class ErrorVerifier:
    descriptor = VerifierDescriptor("error-verifier", "1.0.0", ("observation_contract",))

    def verify(self, obligation, context):
        context.validate_obligation_binding(obligation)
        raise RuntimeError("fixture verifier failure")


@pytest.fixture
def orchestration_graph():
    graph = SemanticGraph()
    graph.add_node(SemanticNode("A", "Module"))
    graph.add_node(SemanticNode("B", "Module"))
    graph.add_edge(SemanticEdge("A", "B", "DEPENDS_ON", metadata={"source_id": "code:1"}))
    return graph


@pytest.fixture
def orchestration_result(orchestration_graph):
    return SemanticGraphAnalysisService(orchestration_graph).analyze(
        GraphQuery("orchestration-query", QueryType.DEPENDENCY, ["A"], {"max_depth": 1})
    )


@pytest.fixture
def observation_obligation(orchestration_result):
    return VerificationObligation.from_analysis_result(
        orchestration_result,
        obligation_type="observation_contract",
        parameters={"subject_id": "A", "predicate": "DEPENDS_ON", "object_id": "B"},
    )


@pytest.fixture
def fallback_registry():
    registry = VerifierRegistry()
    for verifier in (CheapInconclusiveVerifier(), ExpensiveConfirmVerifier()):
        registry.register(verifier)
    return registry


@pytest.fixture
def fallback_service(fallback_registry):
    return VerificationService(fallback_registry)
