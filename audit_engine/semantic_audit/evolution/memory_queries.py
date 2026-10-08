"""Read-only queries over the append-only G3.2 audit-memory ledger."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from audit_engine.semantic_audit.graph.analysis.identity import deterministic_id

from .memory import AuditLongTermMemory, MemoryRecord


MEMORY_QUERY_SCHEMA_VERSION = "semantic_audit_memory_query/v1"


@dataclass(frozen=True)
class MemoryQuery:
    artifact_types: tuple[str, ...] = field(default_factory=tuple)
    artifact_ids: tuple[str, ...] = field(default_factory=tuple)
    snapshot_ids: tuple[str, ...] = field(default_factory=tuple)
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    receipt_ids: tuple[str, ...] = field(default_factory=tuple)
    rule_ids: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_types": list(self.artifact_types),
            "artifact_ids": list(self.artifact_ids),
            "snapshot_ids": list(self.snapshot_ids),
            "evidence_ids": list(self.evidence_ids),
            "receipt_ids": list(self.receipt_ids),
            "rule_ids": list(self.rule_ids),
        }


@dataclass(frozen=True)
class MemoryQueryResult:
    query_id: str
    records: tuple[MemoryRecord, ...]
    schema_version: str = MEMORY_QUERY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "query_id": self.query_id,
            "count": len(self.records),
            "records": [item.to_dict() for item in self.records],
        }


def _payload_values(payload: Mapping[str, Any], key: str) -> set[str]:
    value = payload.get(key)
    if value is None:
        return set()
    if isinstance(value, str):
        return {value}
    if isinstance(value, (tuple, list, set, frozenset)):
        return {str(item) for item in value}
    return {str(value)}


def _evidence_values(payload: Mapping[str, Any]) -> set[str]:
    values = _payload_values(payload, "evidence_ids")
    evidence_records = payload.get("evidence", ())
    if isinstance(evidence_records, (tuple, list)):
        for record in evidence_records:
            if isinstance(record, Mapping):
                evidence_id = record.get("evidence_id")
                if isinstance(evidence_id, str) and evidence_id:
                    values.add(evidence_id)
    return values


class AuditMemoryQueryService:
    def __init__(self, memory: AuditLongTermMemory) -> None:
        self.memory = memory

    def execute(self, query: MemoryQuery) -> MemoryQueryResult:
        wanted_types = set(query.artifact_types)
        wanted_artifacts = set(query.artifact_ids)
        wanted_snapshots = set(query.snapshot_ids)
        wanted_evidence = set(query.evidence_ids)
        wanted_receipts = set(query.receipt_ids)
        wanted_rules = set(query.rule_ids)

        matches = []
        for record in self.memory.all_records():
            payload = record.to_dict()["payload"]
            if wanted_types and record.artifact_type not in wanted_types:
                continue
            if wanted_artifacts and record.artifact_id not in wanted_artifacts:
                continue
            if wanted_snapshots and record.snapshot_id not in wanted_snapshots:
                continue
            if wanted_evidence and not (wanted_evidence & _evidence_values(payload)):
                continue
            receipt_values = _payload_values(payload, "receipt_id") | _payload_values(payload, "receipt_ids")
            if wanted_receipts and not (wanted_receipts & receipt_values):
                continue
            rule_values = _payload_values(payload, "rule_id") | _payload_values(payload, "rule_ids")
            if wanted_rules and not (wanted_rules & rule_values):
                continue
            matches.append(record)

        matches.sort(key=lambda item: item.record_id)
        query_id = deterministic_id("memory-query", query.to_dict(), length=24)
        return MemoryQueryResult(query_id=query_id, records=tuple(matches))
