import pytest

from audit_engine.semantic_audit.evolution import (
    IncrementalReverificationExecutor,
    ReconciliationDisposition,
    ReverificationReplayCatalog,
    TaskExecutionStatus,
)
from audit_engine.semantic_audit.verification import VerificationDecision
from .helpers import build_transition, make_graph


def _execute(after, semantic_context, verification_service, audit_chain):
    before, _, _, catalog, artifacts = audit_chain
    evolution, assessment = build_transition(before, after, semantic_context, artifacts)
    result = IncrementalReverificationExecutor(verification_service).execute(
        evolution=evolution, assessment=assessment, catalog=catalog, after_graph=after,
    )
    return evolution, assessment, result


def test_attribute_change_reexecutes_chain_and_removes_trigger(semantic_context, verification_service, audit_chain):
    _, _, result = _execute(make_graph(target_lifecycle="stable"), semantic_context, verification_service, audit_chain)
    assert result.succeeded
    assert len(result.analyses) == 1
    assert len(result.receipts) == 1
    assert result.receipts[0].decision is VerificationDecision.REFUTED
    assert result.findings == ()
    finding_record = next(x for x in result.task_executions if x.artifact_type == "finding")
    assert finding_record.reconciliation.disposition is ReconciliationDisposition.FINDING_NOT_TRIGGERED


def test_historical_finding_is_not_mutated(semantic_context, verification_service, audit_chain):
    old_finding = audit_chain[2].findings[0]
    _execute(make_graph(target_lifecycle="stable"), semantic_context, verification_service, audit_chain)
    assert old_finding.lifecycle_status.value == "open"


def test_relevant_edge_addition_preserves_finding(semantic_context, verification_service, audit_chain):
    _, _, result = _execute(make_graph(add_extra=True), semantic_context, verification_service, audit_chain)
    finding_record = next(x for x in result.task_executions if x.artifact_type == "finding")
    assert finding_record.status is TaskExecutionStatus.COMPLETED
    assert finding_record.successor_artifact_id is not None
    assert finding_record.reconciliation.disposition is ReconciliationDisposition.FINDING_PERSISTS


def test_removed_rule_target_is_not_applicable(semantic_context, verification_service, audit_chain):
    _, _, result = _execute(make_graph(remove_edge=True), semantic_context, verification_service, audit_chain)
    receipt_record = next(x for x in result.task_executions if x.artifact_type == "verification_receipt")
    finding_record = next(x for x in result.task_executions if x.artifact_type == "finding")
    assert receipt_record.status is TaskExecutionStatus.NOT_APPLICABLE
    assert finding_record.status is TaskExecutionStatus.NOT_APPLICABLE
    assert finding_record.reconciliation.disposition is ReconciliationDisposition.TARGET_NO_LONGER_PRESENT


def test_execution_is_deterministic(semantic_context, verification_service, audit_chain):
    first = _execute(make_graph(target_lifecycle="stable"), semantic_context, verification_service, audit_chain)[2]
    second = _execute(make_graph(target_lifecycle="stable"), semantic_context, verification_service, audit_chain)[2]
    assert first.execution_id == second.execution_id
    assert first.to_dict() == second.to_dict()


def test_execution_rejects_wrong_after_graph(semantic_context, verification_service, audit_chain):
    before, _, _, catalog, artifacts = audit_chain
    after = make_graph(target_lifecycle="stable")
    evolution, assessment = build_transition(before, after, semantic_context, artifacts)
    with pytest.raises(ValueError, match="after snapshot"):
        IncrementalReverificationExecutor(verification_service).execute(
            evolution=evolution, assessment=assessment, catalog=catalog,
            after_graph=make_graph(add_extra=True),
        )


def test_empty_plan_is_successful(semantic_context, verification_service, audit_chain):
    before, _, _, catalog, artifacts = audit_chain
    evolution, assessment = build_transition(before, before, semantic_context, artifacts)
    result = IncrementalReverificationExecutor(verification_service).execute(
        evolution=evolution, assessment=assessment, catalog=catalog, after_graph=before,
    )
    assert result.task_executions == ()
    assert result.succeeded


def test_incomplete_catalog_rejected_before_execution(semantic_context, verification_service, audit_chain):
    before, _, _, _, artifacts = audit_chain
    after = make_graph(target_lifecycle="stable")
    evolution, assessment = build_transition(before, after, semantic_context, artifacts)
    with pytest.raises(ValueError, match="incomplete"):
        IncrementalReverificationExecutor(verification_service).execute(
            evolution=evolution, assessment=assessment,
            catalog=ReverificationReplayCatalog(), after_graph=after,
        )


def test_successor_artifacts_bound_to_after_graph(semantic_context, verification_service, audit_chain):
    evolution, _, result = _execute(make_graph(target_lifecycle="stable"), semantic_context, verification_service, audit_chain)
    assert all(item.graph_fingerprint == evolution.after_snapshot.graph_fingerprint for item in result.analyses)
    assert all(item.graph_fingerprint == evolution.after_snapshot.graph_fingerprint for item in result.receipts)


def test_execution_serializes_reconciliation(semantic_context, verification_service, audit_chain):
    result = _execute(make_graph(target_lifecycle="stable"), semantic_context, verification_service, audit_chain)[2]
    payload = result.to_dict()
    assert payload["schema_version"] == "semantic_reverification_execution/v1"
    assert all("reconciliation" in item for item in payload["task_executions"])
