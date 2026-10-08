"""Append-only durable audit-memory ledger.

The ledger stores immutable serialized audit artifacts and their snapshot
bindings. It is historical memory, not semantic authority: loading a ledger does
not promote candidates, validate findings, or mutate a canonical graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping

from audit_engine.semantic_audit.graph.analysis.identity import deterministic_id

from ._freeze import freeze, thaw


AUDIT_MEMORY_SCHEMA_VERSION = 'semantic_audit_memory/v1'


@dataclass(frozen=True)
class MemoryRecord:
    record_id: str
    artifact_type: str
    artifact_id: str
    snapshot_id: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, 'payload', freeze(dict(self.payload)))

    @classmethod
    def create(
        cls,
        *,
        artifact_type: str,
        artifact_id: str,
        snapshot_id: str,
        payload: Mapping[str, Any],
    ) -> 'MemoryRecord':
        for name, value in {
            'artifact_type': artifact_type,
            'artifact_id': artifact_id,
            'snapshot_id': snapshot_id,
        }.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'{name} must be a non-empty string.')
        canonical_payload = dict(payload)
        identity = {
            'artifact_type': artifact_type,
            'artifact_id': artifact_id,
            'snapshot_id': snapshot_id,
            'payload': canonical_payload,
        }
        return cls(
            record_id=deterministic_id('memory-record', identity, length=28),
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            snapshot_id=snapshot_id,
            payload=canonical_payload,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            'record_id': self.record_id,
            'artifact_type': self.artifact_type,
            'artifact_id': self.artifact_id,
            'snapshot_id': self.snapshot_id,
            'payload': thaw(self.payload),
        }


class AuditLongTermMemory:
    """Append-only record ledger with deterministic JSON persistence."""

    def __init__(self) -> None:
        self._records: dict[str, MemoryRecord] = {}
        self._artifact_index: dict[tuple[str, str], list[str]] = {}
        self._snapshot_index: dict[str, list[str]] = {}

    def append_record(self, record: MemoryRecord) -> MemoryRecord:
        existing = self._records.get(record.record_id)
        if existing is not None:
            if existing.to_dict() != record.to_dict():
                raise ValueError(f'Memory record identity collision: {record.record_id}')
            return existing
        self._records[record.record_id] = record
        self._artifact_index.setdefault((record.artifact_type, record.artifact_id), []).append(record.record_id)
        self._snapshot_index.setdefault(record.snapshot_id, []).append(record.record_id)
        return record

    def append_artifact(
        self,
        *,
        artifact_type: str,
        artifact_id: str,
        snapshot_id: str,
        payload: Mapping[str, Any],
    ) -> MemoryRecord:
        return self.append_record(
            MemoryRecord.create(
                artifact_type=artifact_type,
                artifact_id=artifact_id,
                snapshot_id=snapshot_id,
                payload=payload,
            )
        )

    def records_for_artifact(self, artifact_type: str, artifact_id: str) -> tuple[MemoryRecord, ...]:
        return tuple(
            self._records[record_id]
            for record_id in self._artifact_index.get((artifact_type, artifact_id), ())
        )

    def records_for_snapshot(self, snapshot_id: str) -> tuple[MemoryRecord, ...]:
        return tuple(self._records[record_id] for record_id in self._snapshot_index.get(snapshot_id, ()))

    def get_record(self, record_id: str) -> MemoryRecord | None:
        return self._records.get(record_id)

    def all_records(self) -> tuple[MemoryRecord, ...]:
        return tuple(self._records[key] for key in sorted(self._records))

    def to_dict(self) -> dict[str, Any]:
        return {
            'schema_version': AUDIT_MEMORY_SCHEMA_VERSION,
            'records': [self._records[key].to_dict() for key in sorted(self._records)],
        }

    def write_json(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding='utf-8')

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> 'AuditLongTermMemory':
        if payload.get('schema_version') != AUDIT_MEMORY_SCHEMA_VERSION:
            raise ValueError('Unsupported audit memory schema version.')
        memory = cls()
        for item in payload.get('records', []):
            record = MemoryRecord.create(
                artifact_type=item['artifact_type'],
                artifact_id=item['artifact_id'],
                snapshot_id=item['snapshot_id'],
                payload=item['payload'],
            )
            if item.get('record_id') != record.record_id:
                raise ValueError('Audit memory record identity does not match its content.')
            memory.append_record(record)
        return memory

    @classmethod
    def read_json(cls, path: str | Path) -> 'AuditLongTermMemory':
        return cls.from_dict(json.loads(Path(path).read_text(encoding='utf-8')))

    def __len__(self) -> int:
        return len(self._records)
