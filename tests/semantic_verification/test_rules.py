
from pathlib import Path

import pytest

from audit_engine.semantic_audit.graph.analysis import VerificationStatus
from audit_engine.semantic_audit.rules import (
    RuleDisposition,
    RuleEvaluator,
    RuleLoader,
    SemanticAuditRule,
)
from audit_engine.semantic_audit.verification import (
    ObservationContractVerifier,
    VerificationDecision,
    VerificationObligation,
    VerificationService,
    VerifierRegistry,
)


def _receipt_and_obligation(result, predicate="DEPENDS_ON"):
    obligation = VerificationObligation.from_analysis_result(
        result,
        obligation_type="observation_contract",
        parameters={"subject_id": "A", "predicate": predicate, "object_id": "B"},
    )
    registry = VerifierRegistry()
    registry.register(ObservationContractVerifier())
    receipt = VerificationService(registry).verify(obligation, result)
    return obligation, receipt


def _rule(**overrides):
    values = dict(
        rule_id="architecture.demo",
        version="1.0.0",
        obligation_type="observation_contract",
        title="Demonstration verified relation",
        finding_message="The verified observation satisfies the configured policy trigger.",
    )
    values.update(overrides)
    return SemanticAuditRule(**values)


def test_rule_triggers_only_after_validated_confirmation(dependency_result):
    obligation, receipt = _receipt_and_obligation(dependency_result)
    result = RuleEvaluator().evaluate(_rule(), obligation, receipt)
    assert result.disposition is RuleDisposition.TRIGGERED


def test_refuted_verification_does_not_trigger_rule(dependency_result):
    obligation, receipt = _receipt_and_obligation(dependency_result, predicate="CALLS")
    result = RuleEvaluator().evaluate(_rule(), obligation, receipt)
    assert result.disposition is RuleDisposition.NOT_TRIGGERED


def test_rule_with_wrong_obligation_type_is_ineligible(dependency_result):
    obligation, receipt = _receipt_and_obligation(dependency_result)
    rule = _rule(obligation_type="evidence_corroboration")
    assert RuleEvaluator().evaluate(rule, obligation, receipt).disposition is RuleDisposition.INELIGIBLE


def test_rule_loader_rejects_unknown_fields():
    payload = {
        "rule_id": "r",
        "version": "1",
        "obligation_type": "observation_contract",
        "title": "t",
        "finding_message": "m",
        "execute_python": "dangerous",
    }
    with pytest.raises(ValueError, match="Unknown"):
        RuleLoader.from_mapping(payload)


def test_rule_loader_reads_safe_yaml(tmp_path):
    path = tmp_path / "rule.yaml"
    path.write_text(
        """rule_id: architecture.demo\nversion: 1.0.0\nobligation_type: observation_contract\ntitle: Demo\nfinding_message: Demo finding\nseverity: warning\n""",
        encoding="utf-8",
    )
    rule = RuleLoader.from_yaml(path)
    assert rule.rule_id == "architecture.demo"
    assert rule.severity.value == "warning"


def test_rule_can_require_corroborated_state_without_claiming_validation():
    rule = _rule(minimum_evidence_state=VerificationStatus.CORROBORATED)
    assert rule.minimum_evidence_state is VerificationStatus.CORROBORATED


def test_rule_can_trigger_on_refuted_validated_obligation(dependency_result):
    obligation, receipt = _receipt_and_obligation(dependency_result, predicate="CALLS")
    rule = _rule(trigger_decision=VerificationDecision.REFUTED)
    result = RuleEvaluator().evaluate(rule, obligation, receipt)
    assert receipt.evidence_state is VerificationStatus.VALIDATED
    assert result.disposition is RuleDisposition.TRIGGERED
