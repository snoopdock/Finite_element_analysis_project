"""Strict YAML loader for G3.1.1 domain semantic audit rules."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.verification.models import VerificationDecision

from .domain_models import DomainAuditRule, DomainRuleScope, DomainRuleSelector
from .models import RuleSeverity, SemanticAuditRule


class DomainRuleLoader:
    REQUIRED_FIELDS = {
        "rule_id",
        "version",
        "domain",
        "obligation_type",
        "verifier_id",
        "title",
        "finding_message",
    }
    OPTIONAL_FIELDS = {
        "severity",
        "trigger_decision",
        "minimum_evidence_state",
        "selector",
        "parameters",
        "required_semantic_context",
        "metadata",
    }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> DomainAuditRule:
        missing = sorted(cls.REQUIRED_FIELDS - set(payload))
        if missing:
            raise ValueError("Missing domain audit rule fields: " + ", ".join(missing))
        unknown = sorted(set(payload) - cls.REQUIRED_FIELDS - cls.OPTIONAL_FIELDS)
        if unknown:
            raise ValueError("Unknown domain audit rule fields: " + ", ".join(unknown))

        selector_payload = payload.get("selector", {})
        if not isinstance(selector_payload, Mapping):
            raise ValueError("selector must be a mapping.")
        allowed_selector = {
            "scope", "predicates", "source_entity_types", "target_entity_types"
        }
        selector_unknown = sorted(set(selector_payload) - allowed_selector)
        if selector_unknown:
            raise ValueError("Unknown selector fields: " + ", ".join(selector_unknown))

        def _strings(name: str) -> tuple[str, ...]:
            raw = selector_payload.get(name, ())
            if isinstance(raw, str):
                raw = [raw]
            if not isinstance(raw, (list, tuple)):
                raise ValueError(f"selector.{name} must be a string or sequence.")
            return tuple(str(value) for value in raw)

        try:
            policy = SemanticAuditRule(
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
            selector = DomainRuleSelector(
                scope=DomainRuleScope(selector_payload.get("scope", "observation")),
                predicates=_strings("predicates"),
                source_entity_types=_strings("source_entity_types"),
                target_entity_types=_strings("target_entity_types"),
            )
            parameters = payload.get("parameters", {})
            required_context = payload.get("required_semantic_context", {})
            if not isinstance(parameters, Mapping):
                raise ValueError("parameters must be a mapping.")
            if not isinstance(required_context, Mapping):
                raise ValueError("required_semantic_context must be a mapping.")
            return DomainAuditRule(
                domain=str(payload["domain"]),
                verifier_id=str(payload["verifier_id"]),
                policy=policy,
                selector=selector,
                obligation_parameters=dict(parameters),
                required_semantic_context=dict(required_context),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid domain audit rule: {exc}") from exc

    @classmethod
    def from_yaml(cls, path: str | Path) -> DomainAuditRule:
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Domain audit rule YAML must contain one mapping.")
        return cls.from_mapping(payload)
