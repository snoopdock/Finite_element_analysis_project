
"""Strict loader for declarative semantic audit rules."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.verification.models import VerificationDecision

from .models import RuleSeverity, SemanticAuditRule


class RuleLoader:
    REQUIRED_FIELDS = {
        "rule_id",
        "version",
        "obligation_type",
        "title",
        "finding_message",
    }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> SemanticAuditRule:
        missing = sorted(cls.REQUIRED_FIELDS - set(payload))
        if missing:
            raise ValueError("Missing semantic audit rule fields: " + ", ".join(missing))
        allowed = cls.REQUIRED_FIELDS | {
            "severity",
            "trigger_decision",
            "minimum_evidence_state",
            "metadata",
        }
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ValueError("Unknown semantic audit rule fields: " + ", ".join(unknown))
        try:
            return SemanticAuditRule(
                rule_id=str(payload["rule_id"]),
                version=str(payload["version"]),
                obligation_type=str(payload["obligation_type"]),
                title=str(payload["title"]),
                finding_message=str(payload["finding_message"]),
                severity=RuleSeverity(payload.get("severity", RuleSeverity.ERROR.value)),
                trigger_decision=VerificationDecision(
                    payload.get("trigger_decision", VerificationDecision.CONFIRMED.value)
                ),
                minimum_evidence_state=VerificationStatus(
                    payload.get("minimum_evidence_state", VerificationStatus.VALIDATED.value)
                ),
                metadata=dict(payload.get("metadata", {})),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid semantic audit rule: {exc}") from exc

    @classmethod
    def from_yaml(cls, path: str | Path) -> SemanticAuditRule:
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Semantic audit rule YAML must contain one mapping.")
        return cls.from_mapping(payload)
