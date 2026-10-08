"""Impact-aware invalidation for durable semantic-audit artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from audit_engine.semantic_audit.findings.models import AuditFinding
from audit_engine.semantic_audit.graph.analysis.results import GraphAnalysisResult
from audit_engine.semantic_audit.verification.receipts import VerificationReceipt

from .delta import GraphDelta
from .snapshots import GraphSnapshot


INVALIDATION_REPORT_SCHEMA_VERSION = 'semantic_audit_invalidation/v1'


class ArtifactValidity(str, Enum):
    CURRENT = 'current'
    RECHECK_REQUIRED = 'recheck_required'
    STALE = 'stale'


@dataclass(frozen=True)
class ArtifactInvalidation:
    artifact_type: str
    artifact_id: str
    validity: ArtifactValidity
    reasons: tuple[str, ...] = field(default_factory=tuple)
    affected_evidence_ids: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            'artifact_type': self.artifact_type,
            'artifact_id': self.artifact_id,
            'validity': self.validity.value,
            'reasons': list(self.reasons),
            'affected_evidence_ids': list(self.affected_evidence_ids),
        }


@dataclass(frozen=True)
class InvalidationReport:
    before_snapshot_id: str
    after_snapshot_id: str
    artifacts: tuple[ArtifactInvalidation, ...]
    schema_version: str = INVALIDATION_REPORT_SCHEMA_VERSION

    @property
    def stale_ids(self) -> tuple[str, ...]:
        return tuple(value.artifact_id for value in self.artifacts if value.validity is ArtifactValidity.STALE)

    @property
    def recheck_required_ids(self) -> tuple[str, ...]:
        return tuple(
            value.artifact_id
            for value in self.artifacts
            if value.validity is ArtifactValidity.RECHECK_REQUIRED
        )

    def to_dict(self) -> dict[str, Any]:
        counts = {state.value: 0 for state in ArtifactValidity}
        for artifact in self.artifacts:
            counts[artifact.validity.value] += 1
        return {
            'schema_version': self.schema_version,
            'before_snapshot_id': self.before_snapshot_id,
            'after_snapshot_id': self.after_snapshot_id,
            'summary': counts,
            'artifacts': [value.to_dict() for value in self.artifacts],
        }


def _artifact_identity(artifact) -> tuple[str, str, str, str, tuple[str, ...]]:
    if isinstance(artifact, GraphAnalysisResult):
        return (
            'analysis',
            artifact.analysis_id,
            artifact.graph_fingerprint,
            artifact.semantic_context.fingerprint,
            tuple(record.evidence_id for record in artifact.evidence),
        )
    if isinstance(artifact, VerificationReceipt):
        return (
            'verification_receipt',
            artifact.receipt_id,
            artifact.graph_fingerprint,
            artifact.semantic_context_fingerprint,
            artifact.evidence_ids,
        )
    if isinstance(artifact, AuditFinding):
        return (
            'finding',
            artifact.finding_id,
            artifact.graph_fingerprint,
            artifact.semantic_context_fingerprint,
            artifact.evidence_ids,
        )
    raise TypeError(f'Unsupported audit artifact type: {type(artifact).__name__}')


def _assess_artifact(
    artifact,
    *,
    before: GraphSnapshot,
    after: GraphSnapshot,
    delta: GraphDelta,
) -> ArtifactInvalidation:
    artifact_type, artifact_id, graph_id, context_id, evidence_ids = _artifact_identity(artifact)
    if graph_id != before.graph_fingerprint or context_id != before.semantic_context_fingerprint:
        return ArtifactInvalidation(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            validity=ArtifactValidity.STALE,
            reasons=('artifact_not_bound_to_before_snapshot',),
        )
    if delta.is_noop:
        return ArtifactInvalidation(artifact_type, artifact_id, ArtifactValidity.CURRENT)
    if delta.semantic_context_delta.changed:
        return ArtifactInvalidation(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            validity=ArtifactValidity.STALE,
            reasons=('semantic_context_changed',),
        )
    removed_evidence = tuple(sorted(set(evidence_ids) & set(delta.removed_evidence_ids)))
    if removed_evidence:
        return ArtifactInvalidation(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            validity=ArtifactValidity.STALE,
            reasons=('supporting_evidence_removed',),
            affected_evidence_ids=removed_evidence,
        )
    if before.graph_fingerprint != after.graph_fingerprint:
        return ArtifactInvalidation(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            validity=ArtifactValidity.RECHECK_REQUIRED,
            reasons=('source_graph_changed_without_direct_evidence_loss',),
        )
    return ArtifactInvalidation(artifact_type, artifact_id, ArtifactValidity.CURRENT)


def assess_transition(
    *,
    before: GraphSnapshot,
    after: GraphSnapshot,
    delta: GraphDelta,
    artifacts: Iterable[GraphAnalysisResult | VerificationReceipt | AuditFinding],
) -> InvalidationReport:
    if delta.before_snapshot_id != before.snapshot_id or delta.after_snapshot_id != after.snapshot_id:
        raise ValueError('GraphDelta does not describe the supplied snapshots.')
    assessed = tuple(
        sorted(
            (_assess_artifact(item, before=before, after=after, delta=delta) for item in artifacts),
            key=lambda value: (value.artifact_type, value.artifact_id),
        )
    )
    return InvalidationReport(
        before_snapshot_id=before.snapshot_id,
        after_snapshot_id=after.snapshot_id,
        artifacts=assessed,
    )
