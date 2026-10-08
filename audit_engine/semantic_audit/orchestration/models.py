"""Core contracts for G3.3 cost-aware audit orchestration.

Orchestration chooses *how to spend verification resources*. It does not decide
scientific truth, finding severity, or finding lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from audit_engine.semantic_audit.graph.analysis.identity import deterministic_id
from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus


ORCHESTRATION_PLAN_SCHEMA_VERSION = "semantic_audit_orchestration_plan/v1"
ORCHESTRATION_EXECUTION_SCHEMA_VERSION = "semantic_audit_orchestration_execution/v1"
ORCHESTRATION_POLICY_VERSION = "cost_aware_verification_policy/v1"


class VerificationMethod(str, Enum):
    CONTRACT = "contract"
    CORROBORATION = "corroboration"
    GRAPH_CONSTRAINT = "graph_constraint"
    PROVENANCE = "provenance"
    STATIC_ANALYSIS = "static_analysis"
    SOLVER = "solver"
    EXECUTABLE = "executable"
    EXTERNAL = "external"


class ExecutionMode(str, Enum):
    """Execution containment class, not a trust or correctness score."""

    IN_PROCESS_READ_ONLY = "in_process_read_only"
    SANDBOXED = "sandboxed"
    CONTROLLED_EXTERNAL = "controlled_external"


class OperationalPriority(str, Enum):
    """Queue priority only; never semantic or scientific importance."""

    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


_PRIORITY_ORDER = {
    OperationalPriority.CRITICAL: 0,
    OperationalPriority.HIGH: 1,
    OperationalPriority.NORMAL: 2,
    OperationalPriority.LOW: 3,
}


class RoutePlanningStatus(str, Enum):
    SCHEDULED = "scheduled"
    UNSCHEDULED_NO_CAPABILITY = "unscheduled_no_capability"
    UNSCHEDULED_POLICY = "unscheduled_policy"
    UNSCHEDULED_BUDGET = "unscheduled_budget"


@dataclass(frozen=True)
class VerifierOrchestrationProfile:
    """Policy metadata for one verifier implementation.

    ``cost_units`` are relative, versioned planning units. They are not time,
    currency, probability, confidence, or truth. ``maximum_evidence_state`` is
    a declared capability ceiling, not a guarantee about any particular run.
    """

    verifier_id: str
    verifier_version: str
    method: VerificationMethod
    cost_units: int
    maximum_evidence_state: VerificationStatus
    execution_mode: ExecutionMode = ExecutionMode.IN_PROCESS_READ_ONLY
    deterministic: bool = True
    side_effect_free: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.verifier_id.strip():
            raise ValueError("verifier_id must be non-empty.")
        if not self.verifier_version.strip():
            raise ValueError("verifier_version must be non-empty.")
        if self.cost_units < 1:
            raise ValueError("cost_units must be at least 1.")
        if self.maximum_evidence_state not in {
            VerificationStatus.OBSERVED,
            VerificationStatus.CORROBORATED,
            VerificationStatus.VALIDATED,
        }:
            raise ValueError("maximum_evidence_state must be an affirmative evidence state.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "verifier_id": self.verifier_id,
            "verifier_version": self.verifier_version,
            "method": self.method.value,
            "cost_units": self.cost_units,
            "maximum_evidence_state": self.maximum_evidence_state.value,
            "execution_mode": self.execution_mode.value,
            "deterministic": self.deterministic,
            "side_effect_free": self.side_effect_free,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class AuditBudget:
    """Hard orchestration resource envelope."""

    total_cost_units: int
    max_verifier_runs: int
    allowed_execution_modes: tuple[ExecutionMode, ...] = (
        ExecutionMode.IN_PROCESS_READ_ONLY,
    )

    def __post_init__(self) -> None:
        if self.total_cost_units < 1:
            raise ValueError("total_cost_units must be at least 1.")
        if self.max_verifier_runs < 1:
            raise ValueError("max_verifier_runs must be at least 1.")
        if not self.allowed_execution_modes:
            raise ValueError("At least one execution mode must be allowed.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_cost_units": self.total_cost_units,
            "max_verifier_runs": self.max_verifier_runs,
            "allowed_execution_modes": [item.value for item in self.allowed_execution_modes],
        }


@dataclass(frozen=True)
class VerificationObjective:
    """Operational objective bound to an existing verification obligation."""

    objective_id: str
    obligation_id: str
    minimum_evidence_state: VerificationStatus
    priority: OperationalPriority = OperationalPriority.NORMAL
    allowed_verifier_ids: tuple[str, ...] = field(default_factory=tuple)
    excluded_verifier_ids: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def create(
        cls,
        *,
        obligation_id: str,
        minimum_evidence_state: VerificationStatus,
        priority: OperationalPriority = OperationalPriority.NORMAL,
        allowed_verifier_ids: Sequence[str] = (),
        excluded_verifier_ids: Sequence[str] = (),
    ) -> "VerificationObjective":
        if minimum_evidence_state not in {
            VerificationStatus.OBSERVED,
            VerificationStatus.CORROBORATED,
            VerificationStatus.VALIDATED,
        }:
            raise ValueError("minimum_evidence_state must be observed, corroborated, or validated.")
        allowed = tuple(dict.fromkeys(str(v).strip() for v in allowed_verifier_ids if str(v).strip()))
        excluded = tuple(dict.fromkeys(str(v).strip() for v in excluded_verifier_ids if str(v).strip()))
        if set(allowed) & set(excluded):
            raise ValueError("A verifier cannot be both allowed and excluded.")
        payload = {
            "obligation_id": obligation_id,
            "minimum_evidence_state": minimum_evidence_state.value,
            "priority": priority.value,
            "allowed_verifier_ids": list(allowed),
            "excluded_verifier_ids": list(excluded),
        }
        return cls(
            objective_id=deterministic_id("verification-objective", payload, length=24),
            obligation_id=obligation_id,
            minimum_evidence_state=minimum_evidence_state,
            priority=priority,
            allowed_verifier_ids=allowed,
            excluded_verifier_ids=excluded,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective_id": self.objective_id,
            "obligation_id": self.obligation_id,
            "minimum_evidence_state": self.minimum_evidence_state.value,
            "priority": self.priority.value,
            "allowed_verifier_ids": list(self.allowed_verifier_ids),
            "excluded_verifier_ids": list(self.excluded_verifier_ids),
        }


@dataclass(frozen=True)
class PlannedVerifierAction:
    action_id: str
    verifier_id: str
    verifier_version: str
    method: VerificationMethod
    cost_units: int
    maximum_evidence_state: VerificationStatus
    execution_mode: ExecutionMode

    @classmethod
    def from_profile(cls, objective_id: str, profile: VerifierOrchestrationProfile) -> "PlannedVerifierAction":
        payload = {"objective_id": objective_id, **profile.to_dict()}
        return cls(
            action_id=deterministic_id("orchestration-action", payload, length=24),
            verifier_id=profile.verifier_id,
            verifier_version=profile.verifier_version,
            method=profile.method,
            cost_units=profile.cost_units,
            maximum_evidence_state=profile.maximum_evidence_state,
            execution_mode=profile.execution_mode,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "verifier_id": self.verifier_id,
            "verifier_version": self.verifier_version,
            "method": self.method.value,
            "cost_units": self.cost_units,
            "maximum_evidence_state": self.maximum_evidence_state.value,
            "execution_mode": self.execution_mode.value,
        }


@dataclass(frozen=True)
class VerificationRoute:
    objective: VerificationObjective
    status: RoutePlanningStatus
    actions: tuple[PlannedVerifierAction, ...] = field(default_factory=tuple)
    reason: str | None = None

    @property
    def reserved_cost_units(self) -> int:
        return sum(item.cost_units for item in self.actions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective.to_dict(),
            "status": self.status.value,
            "actions": [item.to_dict() for item in self.actions],
            "reserved_cost_units": self.reserved_cost_units,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class OrchestrationPlan:
    plan_id: str
    policy_version: str
    budget: AuditBudget
    routes: tuple[VerificationRoute, ...]
    schema_version: str = ORCHESTRATION_PLAN_SCHEMA_VERSION

    @property
    def reserved_cost_units(self) -> int:
        return sum(route.reserved_cost_units for route in self.routes)

    @property
    def reserved_verifier_runs(self) -> int:
        return sum(len(route.actions) for route in self.routes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "policy_version": self.policy_version,
            "budget": self.budget.to_dict(),
            "reserved_cost_units": self.reserved_cost_units,
            "reserved_verifier_runs": self.reserved_verifier_runs,
            "routes": [route.to_dict() for route in self.routes],
        }


def priority_sort_key(objective: VerificationObjective) -> tuple[int, str]:
    return (_PRIORITY_ORDER[objective.priority], objective.objective_id)
