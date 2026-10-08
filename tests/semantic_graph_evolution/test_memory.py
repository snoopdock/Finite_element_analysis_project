import json
import pytest

from audit_engine.semantic_audit.evolution import AuditLongTermMemory, GraphSnapshot, MemoryRecord


def test_memory_record_identity_is_deterministic():
    first = MemoryRecord.create(artifact_type='finding', artifact_id='f1', snapshot_id='s1', payload={'x': 1})
    second = MemoryRecord.create(artifact_type='finding', artifact_id='f1', snapshot_id='s1', payload={'x': 1})
    assert first.record_id == second.record_id


def test_memory_append_is_idempotent():
    memory = AuditLongTermMemory()
    record = MemoryRecord.create(artifact_type='finding', artifact_id='f1', snapshot_id='s1', payload={'x': 1})
    memory.append_record(record)
    memory.append_record(record)
    assert len(memory) == 1


def test_memory_indexes_artifact_history():
    memory = AuditLongTermMemory()
    memory.append_artifact(artifact_type='finding', artifact_id='f1', snapshot_id='s1', payload={'state': 'open'})
    memory.append_artifact(artifact_type='finding', artifact_id='f1', snapshot_id='s2', payload={'state': 'stale'})
    records = memory.records_for_artifact('finding', 'f1')
    assert [record.snapshot_id for record in records] == ['s1', 's2']


def test_memory_indexes_snapshot_records():
    memory = AuditLongTermMemory()
    memory.append_artifact(artifact_type='finding', artifact_id='f1', snapshot_id='s1', payload={'x': 1})
    memory.append_artifact(artifact_type='receipt', artifact_id='r1', snapshot_id='s1', payload={'x': 2})
    assert len(memory.records_for_snapshot('s1')) == 2


def test_memory_json_round_trip(tmp_path):
    memory = AuditLongTermMemory()
    memory.append_artifact(artifact_type='finding', artifact_id='f1', snapshot_id='s1', payload={'nested': {'x': [1, 2]}})
    path = tmp_path / 'memory.json'
    memory.write_json(path)
    restored = AuditLongTermMemory.read_json(path)
    assert restored.to_dict() == memory.to_dict()


def test_memory_rejects_tampered_record_identity():
    payload = {
        'schema_version': 'semantic_audit_memory/v1',
        'records': [
            {
                'record_id': 'memory-record:wrong',
                'artifact_type': 'finding',
                'artifact_id': 'f1',
                'snapshot_id': 's1',
                'payload': {'x': 1},
            }
        ],
    }
    with pytest.raises(ValueError, match='identity'):
        AuditLongTermMemory.from_dict(payload)


def test_memory_loading_has_no_graph_side_effect(base_graph, base_context, tmp_path):
    before = GraphSnapshot.capture(base_graph, semantic_context=base_context)
    memory = AuditLongTermMemory()
    memory.append_artifact(artifact_type='snapshot', artifact_id=before.snapshot_id, snapshot_id=before.snapshot_id, payload=before.to_dict())
    path = tmp_path / 'memory.json'
    memory.write_json(path)
    AuditLongTermMemory.read_json(path)
    after = GraphSnapshot.capture(base_graph, semantic_context=base_context)
    assert before.graph_fingerprint == after.graph_fingerprint


def test_memory_rejects_same_record_id_with_different_content():
    memory = AuditLongTermMemory()
    original = MemoryRecord.create(artifact_type='finding', artifact_id='f1', snapshot_id='s1', payload={'x': 1})
    memory.append_record(original)
    forged = MemoryRecord(
        record_id=original.record_id,
        artifact_type='finding',
        artifact_id='f1',
        snapshot_id='s1',
        payload={'x': 2},
    )
    with pytest.raises(ValueError, match='collision'):
        memory.append_record(forged)
