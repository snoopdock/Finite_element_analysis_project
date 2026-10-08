"""Deterministic planning of incremental re-verification work.

The planner produces work *requirements*, not background jobs and not semantic
judgments.  It intentionally does not execute analyzers, verifiers, or rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from audit_engine.semantic_audit.findings.models import AuditFinding
from audit_engine.semantic_audit.graph.analysis.identity import deterministic_id
from audit_engine.semantic_audit.graph.analysis.results import GraphAnalysisResult
from audit_engine.semantic_audit.verification.receipts import VerificationReceipt

from .impact import AuditArtifactDependencyIndex
from .invalidation import ArtifactValidity
from .propagation import ArtifactImpact, ImpactPropagationReport


REVERIFICATION_PLAN_SCHEMA_VERSION = "semantic_reverification_plan/v1"
REVERIFICATION_POLICY_VERSION = "incremental_reverification_policy/v1"


class ReverificationAction(str, Enum):
    RERUN_ANALYSIS = "rerun_analysis"
    REVERIFY_RECEIPT = "reverify_receipt"
    REEVALUATE_FINDING = "reevaluate_finding"


class PriorityBand(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


@dataclass(frozen=True)
class ReverificationPolicy:
    version: str = REVERIFICATION_POLICY_VERSION
    stale_weight: int = 60
    recheck_weight: int = 30
    semantic_context_weight: int = 30
    evidence_loss_weight: int = 25
    source_removal_weight: int = 25
    finding_weight: int = 10
    receipt_weight: int = 5
    severity_weights: Mapping[str, int] = field(
        default_factory=lambda: {
            "critical": 30,
            "high": 20,
            "medium": 10,
            "warning": 8,
            "low": 5,
            "info": 0,
        }
    )


@dataclass(frozen=True)
class ReverificationTask:
    task_id: str
    artifact_type: str
    artifact_id: str
    action: ReverificationAction
    validity: ArtifactValidity
    priority_score: int
    priority_band: PriorityBand
    reasons: tuple[str, ...]
    change_ids: tuple[str, ...]
    prerequisite_artifact_ids: tuple[str, ...] = field(default_factory=tuple)
    policy_version: str = REVERIFICATION_POLICY_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "artifact_type": self.artifact_type,
            "artifact_id": self.artifact_id,
            "action": self.action.value,
            "validity": self.validity.value,
            "priority_score": self.priority_score,
            "priority_band": self.priority_band.value,
            "reasons": list(self.reasons),
            "change_ids": list(self.change_ids),
            "prerequisite_artifact_ids": list(self.prerequisite_artifact_ids),
            "policy_version": self.policy_version,
        }


@dataclass(frozen=True)
class ReverificationPlan:
    plan_id: str
    before_snapshot_id: str
    after_snapshot_id: str
    tasks: tuple[ReverificationTask, ...]
    policy_version: str = REVERIFICATION_POLICY_VERSION
    schema_version: str = REVERIFICATION_PLAN_SCHEMA_VERSION

    @property
    def is_empty(self) -> bool:
        return not self.tasks

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "before_snapshot_id": self.before_snapshot_id,
            "after_snapshot_id": self.after_snapshot_id,
            "policy_version": self.policy_version,
            "is_empty": self.is_empty,
            "tasks": [task.to_dict() for task in self.tasks],
        }


def _action_for(artifact_type: str) -> ReverificationAction:
    if artifact_type == "analysis":
        return ReverificationAction.RERUN_ANALYSIS
    if artifact_type == "verification_receipt":
        return ReverificationAction.REVERIFY_RECEIPT
    if artifact_type == "finding":
        return ReverificationAction.REEVALUATE_FINDING
    raise ValueError(f"Unsupported artifact type for re-verification: {artifact_type}")


def _band(score: int) -> PriorityBand:
    if score >= 100:
        return PriorityBand.CRITICAL
    if score >= 75:
        return PriorityBand.HIGH
    if score >= 45:
        return PriorityBand.NORMAL
    return PriorityBand.LOW


def _score(
    impact: ArtifactImpact,
    artifact,
    policy: ReverificationPolicy,
) -> int:
    score = policy.stale_weight if impact.validity is ArtifactValidity.STALE else policy.recheck_weight
    if "semantic_context_changed" in impact.reasons:
        score += policy.semantic_context_weight
    if "supporting_evidence_removed" in impact.reasons:
        score += policy.evidence_loss_weight
    if "source_entity_removed" in impact.reasons:
        score += policy.source_removal_weight
    if impact.artifact_type == "finding":
        score += policy.finding_weight
        if isinstance(artifact, AuditFinding):
            score += int(policy.severity_weights.get(artifact.severity.lower(), 0))
    elif impact.artifact_type == "verification_receipt":
        score += policy.receipt_weight
    return score


def build_reverification_plan(
    *,
    report: ImpactPropagationReport,
    dependency_index: AuditArtifactDependencyIndex,
    artifacts: Iterable[GraphAnalysisResult | VerificationReceipt | AuditFinding],
    policy: ReverificationPolicy | None = None,
) -> ReverificationPlan:
    policy = policy or ReverificationPolicy()
    artifact_by_id = {}
    for artifact in artifacts:
        artifact_id = (
            artifact.analysis_id if isinstance(artifact, GraphAnalysisResult)
            else artifact.receipt_id if isinstance(artifact, VerificationReceipt)
            else artifact.finding_id
        )
        artifact_by_id[artifact_id] = artifact

    tasks: list[ReverificationTask] = []
    for impact in report.impacts:
        if impact.validity is ArtifactValidity.CURRENT:
            continue
        profile = dependency_index.get(impact.artifact_id)
        if profile is None:
            continue
        score = _score(impact, artifact_by_id.get(impact.artifact_id), policy)
        payload = {
            "artifact_type": impact.artifact_type,
            "artifact_id": impact.artifact_id,
            "action": _action_for(impact.artifact_type).value,
            "validity": impact.validity.value,
            "priority_score": score,
            "reasons": list(impact.reasons),
            "change_ids": list(impact.change_ids),
            "prerequisite_artifact_ids": list(profile.upstream_artifact_ids),
            "policy_version": policy.version,
        }
        tasks.append(
            ReverificationTask(
                task_id=deterministic_id("reverification-task", payload, length=24),
                artifact_type=impact.artifact_type,
                artifact_id=impact.artifact_id,
                action=_action_for(impact.artifact_type),
                validity=impact.validity,
                priority_score=score,
                priority_band=_band(score),
                reasons=impact.reasons,
                change_ids=impact.change_ids,
                prerequisite_artifact_ids=profile.upstream_artifact_ids,
                policy_version=policy.version,
            )
        )

    # Priority is user-facing triage; prerequisites remain explicit and must be
    # respected by a future executor.  This planner does not reorder evidence
    # dependencies into execution claims.
    tasks.sort(key=lambda item: (-item.priority_score, item.artifact_type, item.artifact_id))
    identity = {
        "before_snapshot_id": report.before_snapshot_id,
        "after_snapshot_id": report.after_snapshot_id,
        "policy_version": policy.version,
        "task_ids": [item.task_id for item in tasks],
    }
    return ReverificationPlan(
        plan_id=deterministic_id("reverification-plan", identity, length=28),
        before_snapshot_id=report.before_snapshot_id,
        after_snapshot_id=report.after_snapshot_id,
        tasks=tuple(tasks),
        policy_version=policy.version,
    )
