"""End-to-end execution of declarative domain rules over G3 analysis results."""

from __future__ import annotations

from dataclasses import dataclass, field

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph
from audit_engine.semantic_audit.findings.factory import FindingFactory
from audit_engine.semantic_audit.findings.models import AuditFinding
from audit_engine.semantic_audit.graph.analysis import GraphAnalysisResult
from audit_engine.semantic_audit.verification import (
    VerificationObligation,
    VerificationReceipt,
    VerificationService,
)

from .domain_models import DomainAuditRule, DomainRuleScope
from .evaluator import RuleEvaluator
from .models import RuleDisposition, RuleEvaluationResult


@dataclass(frozen=True)
class DomainRuleExecutionResult:
    rule_id: str
    eligible: bool
    reason: str
    obligations: tuple[VerificationObligation, ...] = field(default_factory=tuple)
    receipts: tuple[VerificationReceipt, ...] = field(default_factory=tuple)
    evaluations: tuple[RuleEvaluationResult, ...] = field(default_factory=tuple)
    findings: tuple[AuditFinding, ...] = field(default_factory=tuple)

    def to_dict(self):
        return {
            "rule_id": self.rule_id,
            "eligible": self.eligible,
            "reason": self.reason,
            "obligations": [item.to_dict() for item in self.obligations],
            "receipts": [item.to_dict() for item in self.receipts],
            "evaluations": [item.to_dict() for item in self.evaluations],
            "findings": [item.to_dict() for item in self.findings],
        }


class DomainRuleExecutor:
    """Route matched graph observations through verification before findings."""

    def __init__(self, verification_service: VerificationService) -> None:
        self.verification_service = verification_service
        self.rule_evaluator = RuleEvaluator()

    @staticmethod
    def _context_matches(rule: DomainAuditRule, result: GraphAnalysisResult) -> bool:
        for key, expected in rule.required_semantic_context.items():
            if getattr(result.semantic_context, key) != expected:
                return False
        return True

    @staticmethod
    def _observation_matches(rule: DomainAuditRule, observation, graph: SemanticGraph) -> bool:
        selector = rule.selector
        if selector.predicates and observation.predicate not in selector.predicates:
            return False
        source = graph.get_node(observation.subject_id)
        target = graph.get_node(observation.object_id)
        if source is None or target is None:
            return False
        if selector.source_entity_types and source.entity_type not in selector.source_entity_types:
            return False
        if selector.target_entity_types and target.entity_type not in selector.target_entity_types:
            return False
        return True

    @staticmethod
    def _analysis_scope_matches(rule: DomainAuditRule, result, graph) -> bool:
        selector = rule.selector
        if not selector.source_entity_types:
            return True
        if not result.source_entities:
            return False
        for node_id in result.source_entities:
            node = graph.get_node(node_id)
            if node is None or node.entity_type not in selector.source_entity_types:
                return False
        return True

    def execute(
        self,
        rule: DomainAuditRule,
        result: GraphAnalysisResult,
        graph: SemanticGraph,
    ) -> DomainRuleExecutionResult:
        if not self._context_matches(rule, result):
            return DomainRuleExecutionResult(
                rule_id=rule.policy.rule_id,
                eligible=False,
                reason="semantic_context_mismatch",
            )

        obligations: list[VerificationObligation] = []
        if rule.selector.scope is DomainRuleScope.OBSERVATION:
            for observation in result.observations:
                if not self._observation_matches(rule, observation, graph):
                    continue
                obligations.append(
                    VerificationObligation.from_analysis_result(
                        result,
                        obligation_type=rule.policy.obligation_type,
                        observation_ids=[observation.observation_id],
                        evidence_ids=list(observation.evidence_ids),
                        requested_verifier_ids=[rule.verifier_id],
                        parameters=rule.obligation_parameters,
                    )
                )
        else:
            if self._analysis_scope_matches(rule, result, graph):
                obligations.append(
                    VerificationObligation.from_analysis_result(
                        result,
                        obligation_type=rule.policy.obligation_type,
                        requested_verifier_ids=[rule.verifier_id],
                        parameters=rule.obligation_parameters,
                    )
                )

        if not obligations:
            return DomainRuleExecutionResult(
                rule_id=rule.policy.rule_id,
                eligible=True,
                reason="no_matching_targets",
            )

        receipts = []
        evaluations = []
        findings = []
        for obligation in obligations:
            receipt = self.verification_service.verify(
                obligation,
                result,
                verifier_id=rule.verifier_id,
                semantic_graph=graph,
            )
            evaluation = self.rule_evaluator.evaluate(rule.policy, obligation, receipt)
            receipts.append(receipt)
            evaluations.append(evaluation)
            if evaluation.disposition is RuleDisposition.TRIGGERED:
                findings.append(FindingFactory.create(rule.policy, evaluation, receipt))

        return DomainRuleExecutionResult(
            rule_id=rule.policy.rule_id,
            eligible=True,
            reason="executed",
            obligations=tuple(obligations),
            receipts=tuple(receipts),
            evaluations=tuple(evaluations),
            findings=tuple(findings),
        )
