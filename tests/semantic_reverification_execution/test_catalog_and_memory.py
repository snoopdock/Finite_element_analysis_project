import pytest

from audit_engine.semantic_audit.evolution import (
    AuditLongTermMemory,
    IncrementalReverificationExecutor,
    ReverificationExecutionMemoryRecorder,
    ReverificationReplayCatalog,
    ReplaySelectionMode,
)
from .helpers import build_transition, make_graph


def test_domain_execution_captures_observation_replay_mode(audit_chain, domain_rule):
    _, analysis, execution, _, _ = audit_chain
    catalog = ReverificationReplayCatalog()
    catalog.add_domain_execution(analysis=analysis, rule=domain_rule, execution=execution)
    assert catalog.selection_modes[execution.obligations[0].obligation_id] is ReplaySelectionMode.OBSERVATION_SEMANTICS


def test_catalog_rejects_conflicting_selection_modes(audit_chain):
    obligation = audit_chain[2].obligations[0]
    catalog = ReverificationReplayCatalog()
    catalog.add_obligation(obligation, selection_mode=ReplaySelectionMode.EXACT_IDS)
    with pytest.raises(ValueError, match="Conflicting"):
        catalog.add_obligation(obligation, selection_mode=ReplaySelectionMode.ANALYSIS_SCOPE)


def test_execution_has_no_automatic_memory_side_effect(semantic_context, verification_service, audit_chain):
    before, _, _, catalog, artifacts = audit_chain
    after = make_graph(target_lifecycle="stable")
    evolution, assessment = build_transition(before, after, semantic_context, artifacts)
    memory = AuditLongTermMemory()
    result = IncrementalReverificationExecutor(verification_service).execute(
        evolution=evolution, assessment=assessment, catalog=catalog, after_graph=after,
    )
    assert len(memory) == 0
    assert result.task_executions


def test_explicit_memory_commit_records_successors(semantic_context, verification_service, audit_chain):
    before, _, _, catalog, artifacts = audit_chain
    after = make_graph(target_lifecycle="stable")
    evolution, assessment = build_transition(before, after, semantic_context, artifacts)
    result = IncrementalReverificationExecutor(verification_service).execute(
        evolution=evolution, assessment=assessment, catalog=catalog, after_graph=after,
    )
    memory = AuditLongTermMemory()
    commit = ReverificationExecutionMemoryRecorder().record(
        memory=memory, result=result, snapshot_id=evolution.after_snapshot.snapshot_id,
    )
    assert commit.execution_id == result.execution_id
    assert len(commit.record_ids) == len(memory)
    assert memory.records_for_artifact("reverification_execution", result.execution_id)


def test_memory_commit_wrong_snapshot_rejected(semantic_context, verification_service, audit_chain):
    before, _, _, catalog, artifacts = audit_chain
    after = make_graph(target_lifecycle="stable")
    evolution, assessment = build_transition(before, after, semantic_context, artifacts)
    result = IncrementalReverificationExecutor(verification_service).execute(
        evolution=evolution, assessment=assessment, catalog=catalog, after_graph=after,
    )
    with pytest.raises(ValueError, match="after snapshot"):
        ReverificationExecutionMemoryRecorder().record(
            memory=AuditLongTermMemory(), result=result, snapshot_id="wrong",
        )


def test_memory_commit_is_idempotent(semantic_context, verification_service, audit_chain):
    before, _, _, catalog, artifacts = audit_chain
    after = make_graph(target_lifecycle="stable")
    evolution, assessment = build_transition(before, after, semantic_context, artifacts)
    result = IncrementalReverificationExecutor(verification_service).execute(
        evolution=evolution, assessment=assessment, catalog=catalog, after_graph=after,
    )
    memory = AuditLongTermMemory()
    recorder = ReverificationExecutionMemoryRecorder()
    first = recorder.record(memory=memory, result=result, snapshot_id=evolution.after_snapshot.snapshot_id)
    size = len(memory)
    second = recorder.record(memory=memory, result=result, snapshot_id=evolution.after_snapshot.snapshot_id)
    assert len(memory) == size
    assert first.record_ids == second.record_ids
