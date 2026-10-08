"""Versioned policy for deterministic, cost-aware verification orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus

from .models import ORCHESTRATION_POLICY_VERSION, VerificationMethod


class SelectionStrategy(str, Enum):
    MINIMUM_COST_SUFFICIENT = "minimum_cost_sufficient"


@dataclass(frozen=True)
class OrchestrationPolicy:
    version: str = ORCHESTRATION_POLICY_VERSION
    selection_strategy: SelectionStrategy = SelectionStrategy.MINIMUM_COST_SUFFICIENT
    require_side_effect_free: bool = True
    allowed_methods: tuple[VerificationMethod, ...] = field(default_factory=lambda: tuple(VerificationMethod))
    fallback_on_inconclusive: bool = True
    fallback_on_error: bool = False
    max_route_length: int = 3

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("policy version must be non-empty.")
        if self.max_route_length < 1:
            raise ValueError("max_route_length must be at least 1.")
        if not self.allowed_methods:
            raise ValueError("allowed_methods must not be empty.")


_EVIDENCE_RANK = {
    VerificationStatus.PROPOSED: 0,
    VerificationStatus.OBSERVED: 1,
    VerificationStatus.CORROBORATED: 2,
    VerificationStatus.VALIDATED: 3,
}


def evidence_rank(value: VerificationStatus) -> int:
    return _EVIDENCE_RANK.get(value, -1)


def evidence_requirement_satisfied(actual: VerificationStatus, required: VerificationStatus) -> bool:
    return evidence_rank(actual) >= evidence_rank(required) >= 0
