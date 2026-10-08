"""Non-destructive reconciliation of replayed audit artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from audit_engine.semantic_audit.findings.models import AuditFinding
from audit_engine.semantic_audit.graph.analysis.results import GraphAnalysisResult
from audit_engine.semantic_audit.rules.models import RuleDisposition
from audit_engine.semantic_audit.verification.receipts import VerificationReceipt


RECONCILIATION_SCHEMA_VERSION = "semantic_artifact_reconciliation/v1"


class ReconciliationDisposition(str, Enum):
    ANALYSIS_EQUIVALENT = "analysis_equivalent"
    ANALYSIS_CHANGED = "analysis_changed"
    RECEIPT_EQUIVALENT = "receipt_equivalent"
    RECEIPT_EVIDENCE_CHANGED = "receipt_evidence_changed"
    RECEIPT_DECISION_CHANGED = "receipt_decision_changed"
    FINDING_PERSISTS = "finding_persists"
    FINDING_NOT_TRIGGERED = "finding_not_triggered"
    FINDING_INELIGIBLE = "finding_ineligible"
    TARGET_NO_LONGER_PRESENT = "target_no_longer_present"
    PREREQUISITE_BLOCKED = "prerequisite_blocked"
    EXECUTION_FAILED = "execution_failed"


@dataclass(frozen=True)
class ArtifactReconciliation:
    artifact_type: str
    predecessor_artifact_id: str
    disposition: ReconciliationDisposition
    successor_artifact_id: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = RECONCILIATION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_type": self.artifact_type,
            "predecessor_artifact_id": self.predecessor_artifact_id,
            "successor_artifact_id": self.successor_artifact_id,
            "disposition": self.disposition.value,
            "details": dict(self.details),
        }


def _analysis_projection(result: GraphAnalysisResult) -> dict[str, Any]:
    return {
        "analysis_type": result.analysis_type.value,
        "status": result.status.value,
        "algorithm": result.algorithm,
        "source_entities": list(result.source_entities),
        "discovered_entities": list(result.discovered_entities),
        "observations": [
            {
                "subject_id": item.subject_id,
                "predicate": item.predicate,
                "object_id": item.object_id,
                "evidence_ids": list(item.evidence_ids),
                "depth": item.depth,
            }
            for item in result.observations
        ],
        "evidence": [
            {
                "evidence_id": item.evidence_id,
                "subject_id": item.subject_id,
                "predicate": item.predicate,
                "object_id": item.object_id,
                "verification_status": item.verification_status.value,
                "provenance": dict(item.provenance),
            }
            for item in result.evidence
        ],
        "parameters": dict(result.parameters),
    }


def reconcile_analysis(predecessor: GraphAnalysisResult, successor: GraphAnalysisResult) -> ArtifactReconciliation:
    equivalent = _analysis_projection(predecessor) == _analysis_projection(successor)
    return ArtifactReconciliation(
        artifact_type="analysis",
        predecessor_artifact_id=predecessor.analysis_id,
        successor_artifact_id=successor.analysis_id,
        disposition=(
            ReconciliationDisposition.ANALYSIS_EQUIVALENT
            if equivalent
            else ReconciliationDisposition.ANALYSIS_CHANGED
        ),
        details={
            "predecessor_graph_fingerprint": predecessor.graph_fingerprint,
            "successor_graph_fingerprint": successor.graph_fingerprint,
            "semantic_projection_equivalent": equivalent,
        },
    )


def reconcile_receipt(predecessor: VerificationReceipt, successor: VerificationReceipt) -> ArtifactReconciliation:
    if predecessor.decision is not successor.decision:
        disposition = ReconciliationDisposition.RECEIPT_DECISION_CHANGED
    else:
        evidence_equivalent = (
            predecessor.evidence_state is successor.evidence_state
            and predecessor.evidence_ids == successor.evidence_ids
            and predecessor.verifier_id == successor.verifier_id
            and predecessor.verifier_version == successor.verifier_version
            and dict(predecessor.details) == dict(successor.details)
            and predecessor.error == successor.error
        )
        disposition = (
            ReconciliationDisposition.RECEIPT_EQUIVALENT
            if evidence_equivalent
            else ReconciliationDisposition.RECEIPT_EVIDENCE_CHANGED
        )
    return ArtifactReconciliation(
        artifact_type="verification_receipt",
        predecessor_artifact_id=predecessor.receipt_id,
        successor_artifact_id=successor.receipt_id,
        disposition=disposition,
        details={
            "predecessor_decision": predecessor.decision.value,
            "successor_decision": successor.decision.value,
            "predecessor_evidence_state": predecessor.evidence_state.value,
            "successor_evidence_state": successor.evidence_state.value,
        },
    )


def reconcile_finding(
    predecessor: AuditFinding,
    *,
    disposition: RuleDisposition,
    successor: AuditFinding | None,
) -> ArtifactReconciliation:
    if disposition is RuleDisposition.TRIGGERED:
        if successor is None:
            raise ValueError("Triggered reconciliation requires a successor finding.")
        value = ReconciliationDisposition.FINDING_PERSISTS
    elif disposition is RuleDisposition.NOT_TRIGGERED:
        value = ReconciliationDisposition.FINDING_NOT_TRIGGERED
    else:
        value = ReconciliationDisposition.FINDING_INELIGIBLE
    return ArtifactReconciliation(
        artifact_type="finding",
        predecessor_artifact_id=predecessor.finding_id,
        successor_artifact_id=successor.finding_id if successor else None,
        disposition=value,
        details={
            "historical_lifecycle_status": predecessor.lifecycle_status.value,
            "lifecycle_mutated": False,
        },
    )


def target_absent_reconciliation(artifact_type: str, artifact_id: str, reason: str) -> ArtifactReconciliation:
    return ArtifactReconciliation(
        artifact_type=artifact_type,
        predecessor_artifact_id=artifact_id,
        disposition=ReconciliationDisposition.TARGET_NO_LONGER_PRESENT,
        details={"reason": reason, "lifecycle_mutated": False},
    )


def blocked_reconciliation(artifact_type: str, artifact_id: str, reason: str) -> ArtifactReconciliation:
    return ArtifactReconciliation(
        artifact_type=artifact_type,
        predecessor_artifact_id=artifact_id,
        disposition=ReconciliationDisposition.PREREQUISITE_BLOCKED,
        details={"reason": reason},
    )


def failed_reconciliation(artifact_type: str, artifact_id: str, reason: str) -> ArtifactReconciliation:
    return ArtifactReconciliation(
        artifact_type=artifact_type,
        predecessor_artifact_id=artifact_id,
        disposition=ReconciliationDisposition.EXECUTION_FAILED,
        details={"reason": reason},
    )
