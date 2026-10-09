import pytest

from audit_engine.semantic_audit.evolution import AuditLongTermMemory, AuditMemoryQueryService, MemoryQuery
from audit_engine.semantic_audit.integration import OrchestrationIntegrationMemoryRecorder, run_budget_aware_reverification
from audit_engine.semantic_audit.orchestration import AuditBudget, OrchestrationPolicy

from .conftest import build_transition, make_graph


def _result(chain, context):
    before, _, _, catalog, artifacts, registry, service, profiles = chain
    after = make_graph(exp1_lifecycle="stable")
    evolution, assessment = build_transition(before, after, context, artifacts)
    result = run_budget_aware_reverification(
        evolution=evolution,
        assessment=assessment,
        catalog=catalog,
        after_graph=after,
        verification_service=service,
        registry=registry,
        profiles=profiles,
        budget=AuditBudget(4, 2),
        orchestration_policy=OrchestrationPolicy(max_route_length=1),
    )
    return evolution, result


def test_orchestration_has_no_implicit_memory_side_effect(two_receipt_chain, semantic_context):
    memory = AuditLongTermMemory()
    _result(two_receipt_chain, semantic_context)
    assert len(memory) == 0


def test_explicit_memory_commit_records_session_and_receipts(two_receipt_chain, semantic_context):
    evolution, result = _result(two_receipt_chain, semantic_context)
    memory = AuditLongTermMemory()
    commit = OrchestrationIntegrationMemoryRecorder().record(
        memory=memory,
        result=result,
        snapshot_id=evolution.after_snapshot.snapshot_id,
    )
    assert commit.record_ids
    types = {record.artifact_type for record in memory.all_records()}
    assert "adaptive_orchestration_session" in types
    assert "reverification_orchestration_preparation" in types
    assert "reverification_orchestration_reconciliation" in types
    assert "verification_receipt" in types
    assert "budget_aware_reverification" in types


def test_explicit_memory_commit_is_idempotent(two_receipt_chain, semantic_context):
    evolution, result = _result(two_receipt_chain, semantic_context)
    memory = AuditLongTermMemory()
    recorder = OrchestrationIntegrationMemoryRecorder()
    one = recorder.record(memory=memory, result=result, snapshot_id=evolution.after_snapshot.snapshot_id)
    size = len(memory)
    two = recorder.record(memory=memory, result=result, snapshot_id=evolution.after_snapshot.snapshot_id)
    assert len(memory) == size
    assert one.record_ids == two.record_ids


def test_memory_commit_rejects_wrong_snapshot(two_receipt_chain, semantic_context):
    _, result = _result(two_receipt_chain, semantic_context)
    with pytest.raises(ValueError, match="after snapshot"):
        OrchestrationIntegrationMemoryRecorder().record(
            memory=AuditLongTermMemory(), result=result, snapshot_id="snapshot:wrong"
        )


def test_existing_memory_query_can_retrieve_orchestration_session(two_receipt_chain, semantic_context):
    evolution, result = _result(two_receipt_chain, semantic_context)
    memory = AuditLongTermMemory()
    OrchestrationIntegrationMemoryRecorder().record(
        memory=memory, result=result, snapshot_id=evolution.after_snapshot.snapshot_id
    )
    query = MemoryQuery(artifact_types=("adaptive_orchestration_session",))
    records = AuditMemoryQueryService(memory).execute(query).records
    assert len(records) == 1
    assert records[0].artifact_id == result.session.session_id
