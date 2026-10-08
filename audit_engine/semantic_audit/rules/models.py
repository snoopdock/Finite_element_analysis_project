
"""Explicit semantic audit rule models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.verification.models import VerificationDecision


class RuleSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class RuleDisposition(str, Enum):
    TRIGGERED = "triggered"
    NOT_TRIGGERED = "not_triggered"
    INELIGIBLE = "ineligible"


@dataclass(frozen=True)
class SemanticAuditRule:
    rule_id: str
    version: str
    obligation_type: str
    title: str
    finding_message: str
    severity: RuleSeverity = RuleSeverity.ERROR
    trigger_decision: VerificationDecision = VerificationDecision.CONFIRMED
    minimum_evidence_state: VerificationStatus = VerificationStatus.VALIDATED
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("rule_id", "version", "obligation_type", "title", "finding_message"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"SemanticAuditRule.{name} must be a non-empty string.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "version": self.version,
            "obligation_type": self.obligation_type,
            "title": self.title,
            "finding_message": self.finding_message,
            "severity": self.severity.value,
            "trigger_decision": self.trigger_decision.value,
            "minimum_evidence_state": self.minimum_evidence_state.value,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RuleEvaluationResult:
    rule_id: str
    rule_version: str
    receipt_id: str
    obligation_id: str
    disposition: RuleDisposition
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "receipt_id": self.receipt_id,
            "obligation_id": self.obligation_id,
            "disposition": self.disposition.value,
            "reason": self.reason,
        }
