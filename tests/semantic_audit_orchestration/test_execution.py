import pytest

from audit_engine.semantic_audit.graph.analysis import VerificationStatus
from audit_engine.semantic_audit.orchestration import (
    AuditBudget,
    ObjectiveExecutionStatus,
    OrchestrationPolicy,
    VerificationMethod,
    VerificationObjective,
    VerifierOrchestrationProfile,
    VerifierProfileCatalog,
    build_orchestration_plan,
    execute_orchestration_plan,
)
from audit_engine.semantic_audit.verification import VerificationService, VerifierRegistry

from .conftest import CheapConfirmVerifier, CheapInconclusiveVerifier, ErrorVerifier, ExpensiveConfirmVerifier


def _profiles(*items):
    catalog = VerifierProfileCatalog()
    for verifier_id, cost in items:
        catalog.register(
            VerifierOrchestrationProfile(
                verifier_id, "1.0.0", VerificationMethod.CONTRACT, cost,
                VerificationStatus.VALIDATED,
            )
        )
    return catalog


def _objective(obligation):
    return VerificationObjective.create(
        obligation_id=obligation.obligation_id,
        minimum_evidence_state=VerificationStatus.VALIDATED,
    )


def _execute(plan, obligation, result, graph, service, policy=None):
    return execute_orchestration_plan(
        plan=plan,
        obligations={obligation.obligation_id: obligation},
        analysis_results={result.analysis_id: result},
        semantic_graphs={result.analysis_id: graph},
        verification_service=service,
        policy=policy,
    )


def test_executor_falls_back_after_inconclusive(observation_obligation, orchestration_result,
                                                 orchestration_graph, fallback_registry):
    profiles = _profiles(("cheap-inconclusive", 1), ("expensive-confirm", 5))
    objective = _objective(observation_obligation)
    plan = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[objective], registry=fallback_registry,
        profiles=profiles, budget=AuditBudget(6, 2),
    )
    result = _execute(
        plan, observation_obligation, orchestration_result, orchestration_graph,
        VerificationService(fallback_registry),
    )
    assert result.objective_results[0].status is ObjectiveExecutionStatus.SATISFIED
    assert [a.verifier_id for a in result.objective_results[0].actions] == [
        "cheap-inconclusive", "expensive-confirm"
    ]
    assert result.consumed_cost_units == 6


def test_executor_stops_after_terminal_primary(observation_obligation, orchestration_result,
                                               orchestration_graph):
    registry = VerifierRegistry()
    registry.register(CheapConfirmVerifier())
    registry.register(ExpensiveConfirmVerifier())
    profiles = _profiles(("cheap-confirm", 1), ("expensive-confirm", 5))
    plan = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[_objective(observation_obligation)],
        registry=registry, profiles=profiles, budget=AuditBudget(6, 2),
    )
    result = _execute(plan, observation_obligation, orchestration_result, orchestration_graph,
                      VerificationService(registry))
    assert len(result.objective_results[0].actions) == 1
    assert result.consumed_cost_units == 1


def test_executor_does_not_fallback_on_error_by_default(observation_obligation,
                                                        orchestration_result, orchestration_graph):
    registry = VerifierRegistry()
    registry.register(ErrorVerifier())
    registry.register(ExpensiveConfirmVerifier())
    profiles = _profiles(("error-verifier", 1), ("expensive-confirm", 5))
    plan = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[_objective(observation_obligation)],
        registry=registry, profiles=profiles, budget=AuditBudget(6, 2),
    )
    result = _execute(plan, observation_obligation, orchestration_result, orchestration_graph,
                      VerificationService(registry))
    assert result.objective_results[0].status is ObjectiveExecutionStatus.FAILED
    assert len(result.objective_results[0].actions) == 1


def test_executor_can_fallback_on_error_when_policy_explicit(observation_obligation,
                                                              orchestration_result, orchestration_graph):
    registry = VerifierRegistry()
    registry.register(ErrorVerifier())
    registry.register(ExpensiveConfirmVerifier())
    profiles = _profiles(("error-verifier", 1), ("expensive-confirm", 5))
    policy = OrchestrationPolicy(fallback_on_error=True)
    plan = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[_objective(observation_obligation)],
        registry=registry, profiles=profiles, budget=AuditBudget(6, 2), policy=policy,
    )
    result = _execute(plan, observation_obligation, orchestration_result, orchestration_graph,
                      VerificationService(registry), policy)
    assert result.objective_results[0].status is ObjectiveExecutionStatus.SATISFIED
    assert len(result.objective_results[0].actions) == 2


def test_execution_identity_is_deterministic(observation_obligation, orchestration_result,
                                             orchestration_graph):
    registry = VerifierRegistry(); registry.register(CheapConfirmVerifier())
    profiles = _profiles(("cheap-confirm", 1))
    plan = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[_objective(observation_obligation)],
        registry=registry, profiles=profiles, budget=AuditBudget(1, 1),
    )
    service = VerificationService(registry)
    first = _execute(plan, observation_obligation, orchestration_result, orchestration_graph, service)
    second = _execute(plan, observation_obligation, orchestration_result, orchestration_graph, service)
    assert first.execution_id == second.execution_id


def test_execution_rejects_policy_version_mismatch(observation_obligation, orchestration_result,
                                                   orchestration_graph):
    registry = VerifierRegistry(); registry.register(CheapConfirmVerifier())
    profiles = _profiles(("cheap-confirm", 1))
    plan = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[_objective(observation_obligation)],
        registry=registry, profiles=profiles, budget=AuditBudget(1, 1),
    )
    with pytest.raises(ValueError, match="policy version"):
        _execute(
            plan, observation_obligation, orchestration_result, orchestration_graph,
            VerificationService(registry), OrchestrationPolicy(version="other/v1")
        )


def test_execution_has_no_automatic_findings_or_memory(observation_obligation,
                                                       orchestration_result, orchestration_graph):
    registry = VerifierRegistry(); registry.register(CheapConfirmVerifier())
    profiles = _profiles(("cheap-confirm", 1))
    plan = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[_objective(observation_obligation)],
        registry=registry, profiles=profiles, budget=AuditBudget(1, 1),
    )
    result = _execute(plan, observation_obligation, orchestration_result, orchestration_graph,
                      VerificationService(registry))
    payload = result.to_dict()
    assert "findings" not in payload
    assert "memory" not in payload
    assert len(result.receipts) == 1
