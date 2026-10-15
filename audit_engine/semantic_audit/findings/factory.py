
"""Guarded creation of findings from triggered rule evaluations."""

from __future__ import annotations

from audit_engine.semantic_audit.graph.analysis.identity import deterministic_id
from audit_engine.semantic_audit.rules.models import (
    RuleDisposition,
    RuleEvaluationResult,
    SemanticAuditRule,
)
from audit_engine.semantic_audit.verification import VerificationReceipt

from .models import AuditFinding


class FindingFactory:
    @staticmethod
    def create_verified(rule, evaluation, receipt, obligation, analysis_result, *, semantic_graph=None):
        """Protected finding admission: independently replay obligation+receipt+rule.

        Callers must supply the current analysis and (when available) its graph.
        Legacy ``create`` remains callable for migration but cannot by itself
        attest source support; protected domain executors use this entrypoint.
        """
        from audit_engine.semantic_audit.verification.models import VerificationContext
        from audit_engine.semantic_audit.verification.integrity import validate_receipt_identity
        from audit_engine.semantic_audit.rules.evaluator import RuleEvaluator
        context=VerificationContext(analysis_result=analysis_result,semantic_graph=semantic_graph)
        context.validate_obligation_binding(obligation)
        validate_receipt_identity(receipt,obligation)
        expected=RuleEvaluator().evaluate(rule,obligation,receipt)
        if (expected.disposition!=evaluation.disposition or
            expected.receipt_id!=evaluation.receipt_id or
            expected.rule_id!=evaluation.rule_id or
            expected.rule_version!=evaluation.rule_version or
            expected.obligation_id!=evaluation.obligation_id):
            raise ValueError('Rule evaluation does not match independently replayed rule')
        if expected.disposition is not RuleDisposition.TRIGGERED:
            raise ValueError('Cannot create verified finding from nontriggered rule')
        return FindingFactory.create(rule,expected,receipt)

    @staticmethod
    def create(
        rule: SemanticAuditRule,
        evaluation: RuleEvaluationResult,
        receipt: VerificationReceipt,
    ) -> AuditFinding:
        if evaluation.disposition is not RuleDisposition.TRIGGERED:
            raise ValueError("An audit finding requires a triggered rule evaluation.")
        if evaluation.receipt_id != receipt.receipt_id:
            raise ValueError("Rule evaluation is bound to a different verification receipt.")
        if evaluation.rule_id != rule.rule_id or evaluation.rule_version != rule.version:
            raise ValueError("Rule evaluation is bound to a different rule.")
        payload = {
            "rule_id": rule.rule_id,
            "rule_version": rule.version,
            "receipt_id": receipt.receipt_id,
            "obligation_id": receipt.obligation_id,
            "graph_fingerprint": receipt.graph_fingerprint,
            "semantic_context_fingerprint": receipt.semantic_context_fingerprint,
        }
        return AuditFinding(
            finding_id=deterministic_id("finding", payload, length=24),
            rule_id=rule.rule_id,
            rule_version=rule.version,
            receipt_id=receipt.receipt_id,
            obligation_id=receipt.obligation_id,
            severity=rule.severity.value,
            title=rule.title,
            message=rule.finding_message,
            evidence_ids=receipt.evidence_ids,
            graph_fingerprint=receipt.graph_fingerprint,
            semantic_context_fingerprint=receipt.semantic_context_fingerprint,
            metadata={"rule_evaluation_reason": evaluation.reason},
        )
