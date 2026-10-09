import pytest

from audit_engine.semantic_audit.graph.analysis import VerificationStatus
from audit_engine.semantic_audit.integration import (
    BridgeTaskStatus,
    ReverificationOrchestrationBridgePolicy,
    prepare_reverification_orchestration,
)

from .conftest import build_transition, make_graph


def _prepare(chain, context, after):
    before, _, _, catalog, artifacts, *_ = chain
    evolution, assessment = build_transition(before, after, context, artifacts)
    preparation = prepare_reverification_orchestration(
        evolution=evolution, assessment=assessment, catalog=catalog, after_graph=after
    )
    return evolution, assessment, preparation


def test_preparation_replays_impacted_analysis_and_rebases_receipts(two_receipt_chain, semantic_context):
    evolution, _, preparation = _prepare(
        two_receipt_chain, semantic_context, make_graph(exp1_lifecycle="stable")
    )
    assert preparation.after_snapshot_id == evolution.after_snapshot.snapshot_id
    assert len(preparation.analyses) == 1
    assert len(preparation.obligations) == 2
    assert len(preparation.objectives) == 2
    assert len(preparation.bindings) == 2
    assert all(
        item.graph_fingerprint == evolution.after_snapshot.graph_fingerprint
        for item in preparation.analyses
    )
    assert all(
        item.graph_fingerprint == evolution.after_snapshot.graph_fingerprint
        for item in preparation.obligations
    )


def test_bridge_preserves_historical_requested_verifier_authority(two_receipt_chain, semantic_context):
    _, _, execution, _, _, *_ = two_receipt_chain
    _, _, preparation = _prepare(
        two_receipt_chain, semantic_context, make_graph(exp1_lifecycle="stable")
    )
    historical = {item.obligation_id: item for item in execution.obligations}
    assert all(binding.requested_verifier_ids == ("graph-attribute-constraint",) for binding in preparation.bindings)
    assert all(item.requested_verifier_ids == ("graph-attribute-constraint",) for item in preparation.obligations)
    assert all(item.requested_verifier_ids for item in historical.values())


def test_bridge_uses_prior_affirmative_evidence_state_as_minimum(two_receipt_chain, semantic_context):
    _, _, preparation = _prepare(
        two_receipt_chain, semantic_context, make_graph(exp1_lifecycle="stable")
    )
    assert {item.minimum_evidence_state for item in preparation.objectives} == {VerificationStatus.VALIDATED}


def test_bridge_policy_does_not_authorize_verifier_substitution():
    with pytest.raises(ValueError, match="does not authorize verifier substitution"):
        ReverificationOrchestrationBridgePolicy(preserve_requested_verifiers=False)


def test_removed_semantic_target_is_not_scheduled(two_receipt_chain, semantic_context):
    _, _, preparation = _prepare(
        two_receipt_chain, semantic_context, make_graph(include_exp1=False)
    )
    receipt_records = [
        item for item in preparation.task_records if item.artifact_type == "verification_receipt"
    ]
    assert any(item.status is BridgeTaskStatus.NOT_APPLICABLE for item in receipt_records)
    assert len(preparation.objectives) < len(two_receipt_chain[2].receipts)


def test_preparation_identity_is_deterministic(two_receipt_chain, semantic_context):
    after = make_graph(exp1_lifecycle="stable")
    first = _prepare(two_receipt_chain, semantic_context, after)[2]
    second = _prepare(two_receipt_chain, semantic_context, after)[2]
    assert first.preparation_id == second.preparation_id
    assert first.to_dict() == second.to_dict()
