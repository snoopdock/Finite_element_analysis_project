"""Domain rule contracts that bind declarative policy to explicit verifiers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from .models import SemanticAuditRule


class DomainRuleScope(str, Enum):
    OBSERVATION = "observation"
    ANALYSIS = "analysis"


@dataclass(frozen=True)
class DomainRuleSelector:
    scope: DomainRuleScope = DomainRuleScope.OBSERVATION
    predicates: tuple[str, ...] = field(default_factory=tuple)
    source_entity_types: tuple[str, ...] = field(default_factory=tuple)
    target_entity_types: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "predicates",
            tuple(dict.fromkeys(value.strip() for value in self.predicates if value.strip())),
        )
        object.__setattr__(
            self,
            "source_entity_types",
            tuple(dict.fromkeys(value.strip() for value in self.source_entity_types if value.strip())),
        )
        object.__setattr__(
            self,
            "target_entity_types",
            tuple(dict.fromkeys(value.strip() for value in self.target_entity_types if value.strip())),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope.value,
            "predicates": list(self.predicates),
            "source_entity_types": list(self.source_entity_types),
            "target_entity_types": list(self.target_entity_types),
        }


@dataclass(frozen=True)
class DomainAuditRule:
    """Declarative domain rule plus verifier routing information."""

    domain: str
    verifier_id: str
    policy: SemanticAuditRule
    selector: DomainRuleSelector = field(default_factory=DomainRuleSelector)
    obligation_parameters: Mapping[str, Any] = field(default_factory=dict)
    required_semantic_context: Mapping[str, str | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.domain.strip():
            raise ValueError("DomainAuditRule.domain must be non-empty.")
        if not self.verifier_id.strip():
            raise ValueError("DomainAuditRule.verifier_id must be non-empty.")
        allowed_context = {
            "graph_schema_version",
            "relationship_vocabulary_version",
            "projection_contract_version",
            "analysis_contract_version",
        }
        unknown = set(self.required_semantic_context) - allowed_context
        if unknown:
            raise ValueError(
                "Unknown semantic context requirement(s): " + ", ".join(sorted(unknown))
            )

    def to_dict(self) -> dict[str, Any]:
        payload = self.policy.to_dict()
        payload.update(
            {
                "domain": self.domain,
                "verifier_id": self.verifier_id,
                "selector": self.selector.to_dict(),
                "parameters": dict(self.obligation_parameters),
                "required_semantic_context": dict(self.required_semantic_context),
            }
        )
        return payload
