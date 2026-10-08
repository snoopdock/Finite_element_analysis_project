
"""Rule evaluation over immutable verification receipts."""

from __future__ import annotations

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.verification import VerificationObligation, VerificationReceipt

from .models import RuleDisposition, RuleEvaluationResult, SemanticAuditRule


_EVIDENCE_RANK = {
    VerificationStatus.PROPOSED: 0,
    VerificationStatus.OBSERVED: 1,
    VerificationStatus.CORROBORATED: 2,
    VerificationStatus.VALIDATED: 3,
}


class RuleEvaluator:
    """Evaluate whether one verified obligation satisfies a declarative rule.

    The evaluator never re-runs graph algorithms and never upgrades evidence.
    """

    def evaluate(
        self,
        rule: SemanticAuditRule,
        obligation: VerificationObligation,
        receipt: VerificationReceipt,
    ) -> RuleEvaluationResult:
        if receipt.obligation_id != obligation.obligation_id:
            raise ValueError("Receipt and obligation do not match.")
        if rule.obligation_type != obligation.obligation_type:
            return RuleEvaluationResult(
                rule.rule_id,
                rule.version,
                receipt.receipt_id,
                obligation.obligation_id,
                RuleDisposition.INELIGIBLE,
                "Rule obligation type does not match verification obligation.",
            )
        actual_rank = _EVIDENCE_RANK.get(receipt.evidence_state)
        required_rank = _EVIDENCE_RANK.get(rule.minimum_evidence_state)
        if actual_rank is None or required_rank is None or actual_rank < required_rank:
            return RuleEvaluationResult(
                rule.rule_id,
                rule.version,
                receipt.receipt_id,
                obligation.obligation_id,
                RuleDisposition.INELIGIBLE,
                "Verification evidence state is below the rule requirement.",
            )
        if receipt.decision is rule.trigger_decision:
            return RuleEvaluationResult(
                rule.rule_id,
                rule.version,
                receipt.receipt_id,
                obligation.obligation_id,
                RuleDisposition.TRIGGERED,
                "Verified obligation satisfies the rule trigger decision.",
            )
        return RuleEvaluationResult(
            rule.rule_id,
            rule.version,
            receipt.receipt_id,
            obligation.obligation_id,
            RuleDisposition.NOT_TRIGGERED,
            "Verification decision does not satisfy the rule trigger decision.",
        )
