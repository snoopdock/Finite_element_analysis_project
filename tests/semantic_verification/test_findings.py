
import pytest

from audit_engine.semantic_audit.findings import (
    FindingFactory,
    FindingLifecycleStatus,
    mark_stale_if_context_changed,
    transition_finding,
)
from audit_engine.semantic_audit.rules import RuleEvaluator, SemanticAuditRule
from audit_engine.semantic_audit.verification import (
    ObservationContractVerifier,
    VerificationObligation,
    VerificationService,
    VerifierRegistry,
)


def _artifacts(result, predicate="DEPENDS_ON"):
    obligation = VerificationObligation.from_analysis_result(
        result,
        obligation_type="observation_contract",
        parameters={"subject_id": "A", "predicate": predicate, "object_id": "B"},
    )
    registry = VerifierRegistry()
    registry.register(ObservationContractVerifier())
    receipt = VerificationService(registry).verify(obligation, result)
    rule = SemanticAuditRule(
        rule_id="architecture.demo",
        version="1.0.0",
        obligation_type="observation_contract",
        title="Verified demonstration condition",
        finding_message="A verified condition matched the demonstration policy.",
    )
    evaluation = RuleEvaluator().evaluate(rule, obligation, receipt)
    return obligation, receipt, rule, evaluation


def test_finding_requires_triggered_rule_evaluation(dependency_result):
    _, receipt, rule, evaluation = _artifacts(dependency_result, predicate="CALLS")
    with pytest.raises(ValueError, match="triggered"):
        FindingFactory.create(rule, evaluation, receipt)


def test_finding_is_bound_to_receipt_rule_and_context(dependency_result):
    obligation, receipt, rule, evaluation = _artifacts(dependency_result)
    finding = FindingFactory.create(rule, evaluation, receipt)
    assert finding.receipt_id == receipt.receipt_id
    assert finding.obligation_id == obligation.obligation_id
    assert finding.graph_fingerprint == receipt.graph_fingerprint
    assert finding.semantic_context_fingerprint == receipt.semantic_context_fingerprint
    assert finding.lifecycle_status is FindingLifecycleStatus.OPEN


def test_finding_identity_is_deterministic(dependency_result):
    _, receipt, rule, evaluation = _artifacts(dependency_result)
    assert FindingFactory.create(rule, evaluation, receipt).finding_id == FindingFactory.create(rule, evaluation, receipt).finding_id


def test_finding_lifecycle_allows_open_to_acknowledged(dependency_result):
    _, receipt, rule, evaluation = _artifacts(dependency_result)
    finding = FindingFactory.create(rule, evaluation, receipt)
    changed = transition_finding(finding, FindingLifecycleStatus.ACKNOWLEDGED)
    assert changed.lifecycle_status is FindingLifecycleStatus.ACKNOWLEDGED


def test_finding_lifecycle_rejects_stale_to_open(dependency_result):
    _, receipt, rule, evaluation = _artifacts(dependency_result)
    finding = FindingFactory.create(rule, evaluation, receipt)
    stale = transition_finding(finding, FindingLifecycleStatus.STALE)
    with pytest.raises(ValueError, match="Invalid"):
        transition_finding(stale, FindingLifecycleStatus.OPEN)


def test_finding_marked_stale_when_graph_changes(dependency_result):
    _, receipt, rule, evaluation = _artifacts(dependency_result)
    finding = FindingFactory.create(rule, evaluation, receipt)
    stale = mark_stale_if_context_changed(
        finding,
        graph_fingerprint="graph:new",
        semantic_context_fingerprint=finding.semantic_context_fingerprint,
    )
    assert stale.lifecycle_status is FindingLifecycleStatus.STALE
