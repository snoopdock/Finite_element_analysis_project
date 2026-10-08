
"""Audit findings produced only after rule evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


AUDIT_FINDING_SCHEMA_VERSION = "semantic_audit_finding/v1"


class FindingLifecycleStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"
    STALE = "stale"


@dataclass(frozen=True)
class AuditFinding:
    finding_id: str
    rule_id: str
    rule_version: str
    receipt_id: str
    obligation_id: str
    severity: str
    title: str
    message: str
    evidence_ids: tuple[str, ...]
    graph_fingerprint: str
    semantic_context_fingerprint: str
    lifecycle_status: FindingLifecycleStatus = FindingLifecycleStatus.OPEN
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = AUDIT_FINDING_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "finding_id": self.finding_id,
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "receipt_id": self.receipt_id,
            "obligation_id": self.obligation_id,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "evidence_ids": list(self.evidence_ids),
            "graph_fingerprint": self.graph_fingerprint,
            "semantic_context_fingerprint": self.semantic_context_fingerprint,
            "lifecycle_status": self.lifecycle_status.value,
            "metadata": dict(self.metadata),
        }
