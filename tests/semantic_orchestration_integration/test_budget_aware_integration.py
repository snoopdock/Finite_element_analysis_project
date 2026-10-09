from audit_engine.semantic_audit.integration import (
    OrchestratedReceiptStatus,
    run_budget_aware_reverification,
)
from audit_engine.semantic_audit.orchestration import AdaptiveReplanningPolicy, AuditBudget, OrchestrationPolicy
from audit_engine.semantic_audit.verification import VerificationDecision

from .conftest import build_transition, make_graph


def _run(chain, context, after, *, budget):
    before, _, _, catalog, artifacts, registry, service, profiles = chain
    evolution, assessment = build_transition(before, after, context, artifacts)
    result = run_budget_aware_reverification(
        evolution=evolution,
        assessment=assessment,
        catalog=catalog,
        after_graph=after,
        verification_service=service,
        registry=registry,
        profiles=profiles,
        budget=budget,
        orchestration_policy=OrchestrationPolicy(max_route_length=1),
        adaptive_policy=AdaptiveReplanningPolicy(max_replanning_rounds=1),
    )
    return evolution, assessment, result


def test_budget_aware_reverification_reconciles_successor_receipts(two_receipt_chain, semantic_context):
    _, _, result = _run(
        two_receipt_chain,
        semantic_context,
        make_graph(exp1_lifecycle="stable"),
        budget=AuditBudget(4, 2),
    )
    assert len(result.reconciliation.successor_receipts) == 2
    assert result.reconciliation.unresolved_task_ids == ()
    assert all(
        item.status is OrchestratedReceiptStatus.RECONCILED
        for item in result.reconciliation.items
        if item.objective_id is not None
    )
    assert {item.decision for item in result.reconciliation.successor_receipts} == {
        VerificationDecision.CONFIRMED,
        VerificationDecision.REFUTED,
    }


def test_shared_budget_can_leave_lower_coverage_work_unsatisfied(two_receipt_chain, semantic_context):
    _, _, result = _run(
        two_receipt_chain,
        semantic_context,
        make_graph(exp1_lifecycle="stable"),
        budget=AuditBudget(2, 1),
    )
    statuses = [item.status for item in result.reconciliation.items if item.objective_id is not None]
    assert statuses.count(OrchestratedReceiptStatus.RECONCILED) == 1
    assert statuses.count(OrchestratedReceiptStatus.UNSATISFIED) == 1
    assert len(result.reconciliation.unresolved_task_ids) == 1
    assert result.session.total_consumed_cost_units <= 2
    assert result.session.total_consumed_verifier_runs <= 1


def test_integration_stops_at_receipts_not_findings(two_receipt_chain, semantic_context):
    _, _, result = _run(
        two_receipt_chain,
        semantic_context,
        make_graph(exp1_lifecycle="stable"),
        budget=AuditBudget(4, 2),
    )
    payload = result.to_dict()
    assert "findings" not in payload
    assert "evaluations" not in payload
    assert "promotions" not in payload


def test_result_identity_is_deterministic(two_receipt_chain, semantic_context):
    after = make_graph(exp1_lifecycle="stable")
    first = _run(two_receipt_chain, semantic_context, after, budget=AuditBudget(4, 2))[2]
    second = _run(two_receipt_chain, semantic_context, after, budget=AuditBudget(4, 2))[2]
    assert first.result_id == second.result_id
    assert first.to_dict() == second.to_dict()


def test_target_removal_does_not_consume_verifier_budget_for_absent_target(two_receipt_chain, semantic_context):
    _, _, result = _run(
        two_receipt_chain,
        semantic_context,
        make_graph(include_exp1=False),
        budget=AuditBudget(4, 2),
    )
    assert any(item.status is OrchestratedReceiptStatus.NOT_APPLICABLE for item in result.reconciliation.items)
    assert result.session.total_consumed_verifier_runs <= 1
