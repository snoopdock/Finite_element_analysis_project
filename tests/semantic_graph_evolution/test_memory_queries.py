from audit_engine.semantic_audit.evolution import AuditLongTermMemory, AuditMemoryQueryService, MemoryQuery


def _memory():
    memory = AuditLongTermMemory()
    memory.append_artifact(
        artifact_type='analysis', artifact_id='analysis:1', snapshot_id='snap:1',
        payload={'evidence_ids': ['e1', 'e2'], 'query_id': 'q1'},
    )
    memory.append_artifact(
        artifact_type='verification_receipt', artifact_id='receipt:1', snapshot_id='snap:1',
        payload={'evidence_ids': ['e1'], 'receipt_id': 'receipt:1', 'verifier_id': 'v'},
    )
    memory.append_artifact(
        artifact_type='finding', artifact_id='finding:1', snapshot_id='snap:1',
        payload={'evidence_ids': ['e1'], 'receipt_id': 'receipt:1', 'rule_id': 'rule:A'},
    )
    memory.append_artifact(
        artifact_type='finding', artifact_id='finding:2', snapshot_id='snap:2',
        payload={'evidence_ids': ['e3'], 'receipt_id': 'receipt:2', 'rule_id': 'rule:B'},
    )
    return memory


def test_memory_exposes_deterministic_read_only_record_view():
    memory = _memory()
    one = memory.all_records()
    two = memory.all_records()
    assert one == two
    assert tuple(item.record_id for item in one) == tuple(sorted(item.record_id for item in one))


def test_query_by_snapshot():
    result = AuditMemoryQueryService(_memory()).execute(MemoryQuery(snapshot_ids=('snap:2',)))
    assert [item.artifact_id for item in result.records] == ['finding:2']


def test_query_by_artifact_type():
    result = AuditMemoryQueryService(_memory()).execute(MemoryQuery(artifact_types=('finding',)))
    assert {item.artifact_id for item in result.records} == {'finding:1', 'finding:2'}


def test_query_by_evidence_id():
    result = AuditMemoryQueryService(_memory()).execute(MemoryQuery(evidence_ids=('e1',)))
    assert {item.artifact_id for item in result.records} == {'analysis:1', 'receipt:1', 'finding:1'}


def test_query_by_receipt_id():
    result = AuditMemoryQueryService(_memory()).execute(MemoryQuery(receipt_ids=('receipt:1',)))
    assert {item.artifact_id for item in result.records} == {'receipt:1', 'finding:1'}


def test_query_by_rule_id():
    result = AuditMemoryQueryService(_memory()).execute(MemoryQuery(rule_ids=('rule:B',)))
    assert [item.artifact_id for item in result.records] == ['finding:2']


def test_query_filters_are_anded():
    result = AuditMemoryQueryService(_memory()).execute(
        MemoryQuery(artifact_types=('finding',), snapshot_ids=('snap:1',), evidence_ids=('e1',))
    )
    assert [item.artifact_id for item in result.records] == ['finding:1']


def test_query_identity_is_deterministic():
    service = AuditMemoryQueryService(_memory())
    query = MemoryQuery(rule_ids=('rule:A',))
    assert service.execute(query).query_id == service.execute(query).query_id


def test_memory_query_does_not_mutate_ledger():
    memory = _memory()
    size = len(memory)
    AuditMemoryQueryService(memory).execute(MemoryQuery(evidence_ids=('e1',)))
    assert len(memory) == size


def test_query_evidence_supports_serialized_analysis_shape():
    memory = AuditLongTermMemory()
    memory.append_artifact(
        artifact_type='analysis', artifact_id='analysis:serialized', snapshot_id='snap:1',
        payload={'evidence': [{'evidence_id': 'edge:real', 'subject_id': 'a'}]},
    )
    result = AuditMemoryQueryService(memory).execute(MemoryQuery(evidence_ids=('edge:real',)))
    assert [item.artifact_id for item in result.records] == ['analysis:serialized']
