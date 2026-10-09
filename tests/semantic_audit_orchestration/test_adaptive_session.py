from audit_engine.semantic_audit.graph.analysis import VerificationStatus
from audit_engine.semantic_audit.orchestration import (
    AdaptiveReplanningPolicy,
    AdaptiveSessionStatus,
    AuditBudget,
    OrchestrationPolicy,
    VerificationMethod,
    VerificationObjective,
    VerifierOrchestrationProfile,
    VerifierProfileCatalog,
    build_orchestration_plan,
    run_adaptive_orchestration,
)
from audit_engine.semantic_audit.verification import VerificationService, VerifierRegistry

from .conftest import CheapConfirmVerifier, CheapInconclusiveVerifier, ErrorVerifier, ExpensiveConfirmVerifier


def _profile(verifier_id, cost):
    return VerifierOrchestrationProfile(
        verifier_id, "1.0.0", VerificationMethod.CONTRACT, cost, VerificationStatus.VALIDATED
    )


def _catalog(*profiles):
    catalog = VerifierProfileCatalog()
    for profile in profiles:
        catalog.register(profile)
    return catalog


def _objective(obligation):
    return VerificationObjective.create(
        obligation_id=obligation.obligation_id,
        minimum_evidence_state=VerificationStatus.VALIDATED,
    )


def test_adaptive_session_escalates_after_inconclusive(observation_obligation, orchestration_result):
    registry = VerifierRegistry(); registry.register(CheapInconclusiveVerifier()); registry.register(ExpensiveConfirmVerifier())
    catalog = _catalog(_profile("cheap-inconclusive", 1), _profile("expensive-confirm", 5))
    objective = _objective(observation_obligation)
    policy = OrchestrationPolicy(max_route_length=1)
    initial = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[objective], registry=registry,
        profiles=catalog, budget=AuditBudget(6, 2), policy=policy,
    )
    result = run_adaptive_orchestration(
        initial_plan=initial,
        obligations={observation_obligation.obligation_id: observation_obligation},
        analysis_results={orchestration_result.analysis_id: orchestration_result},
        verification_service=VerificationService(registry),
        registry=registry, profiles=catalog, orchestration_policy=policy,
    )
    assert result.status is AdaptiveSessionStatus.SATISFIED
    assert len(result.executions) == 2
    assert len(result.replans) == 1
    assert result.total_consumed_cost_units == 6
    assert result.total_consumed_verifier_runs == 2
    assert result.remaining_cost_units == 0


def test_adaptive_session_stops_after_initial_success(observation_obligation, orchestration_result):
    registry = VerifierRegistry(); registry.register(CheapConfirmVerifier())
    catalog = _catalog(_profile("cheap-confirm", 1))
    objective = _objective(observation_obligation)
    policy = OrchestrationPolicy(max_route_length=1)
    initial = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[objective], registry=registry,
        profiles=catalog, budget=AuditBudget(5, 3), policy=policy,
    )
    result = run_adaptive_orchestration(
        initial_plan=initial,
        obligations={observation_obligation.obligation_id: observation_obligation},
        analysis_results={orchestration_result.analysis_id: orchestration_result},
        verification_service=VerificationService(registry),
        registry=registry, profiles=catalog, orchestration_policy=policy,
    )
    assert result.status is AdaptiveSessionStatus.SATISFIED
    assert len(result.executions) == 1
    assert result.replans == ()


def test_adaptive_session_never_exceeds_original_budget(observation_obligation, orchestration_result):
    registry = VerifierRegistry(); registry.register(CheapInconclusiveVerifier()); registry.register(ExpensiveConfirmVerifier())
    catalog = _catalog(_profile("cheap-inconclusive", 1), _profile("expensive-confirm", 5))
    objective = _objective(observation_obligation)
    policy = OrchestrationPolicy(max_route_length=1)
    initial = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[objective], registry=registry,
        profiles=catalog, budget=AuditBudget(1, 1), policy=policy,
    )
    result = run_adaptive_orchestration(
        initial_plan=initial,
        obligations={observation_obligation.obligation_id: observation_obligation},
        analysis_results={orchestration_result.analysis_id: orchestration_result},
        verification_service=VerificationService(registry),
        registry=registry, profiles=catalog, orchestration_policy=policy,
    )
    assert result.status is AdaptiveSessionStatus.BUDGET_EXHAUSTED
    assert result.total_consumed_cost_units == 1
    assert result.total_consumed_verifier_runs == 1


def test_adaptive_session_failure_does_not_escalate_without_policy(observation_obligation, orchestration_result):
    registry = VerifierRegistry(); registry.register(ErrorVerifier()); registry.register(ExpensiveConfirmVerifier())
    catalog = _catalog(_profile("error-verifier", 1), _profile("expensive-confirm", 5))
    objective = _objective(observation_obligation)
    policy = OrchestrationPolicy(max_route_length=1)
    initial = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[objective], registry=registry,
        profiles=catalog, budget=AuditBudget(6, 2), policy=policy,
    )
    result = run_adaptive_orchestration(
        initial_plan=initial,
        obligations={observation_obligation.obligation_id: observation_obligation},
        analysis_results={orchestration_result.analysis_id: orchestration_result},
        verification_service=VerificationService(registry),
        registry=registry, profiles=catalog, orchestration_policy=policy,
    )
    assert result.status is AdaptiveSessionStatus.POLICY_STOPPED
    assert len(result.executions) == 1


def test_adaptive_session_can_escalate_after_failure_when_explicit(observation_obligation, orchestration_result):
    registry = VerifierRegistry(); registry.register(ErrorVerifier()); registry.register(ExpensiveConfirmVerifier())
    catalog = _catalog(_profile("error-verifier", 1), _profile("expensive-confirm", 5))
    objective = _objective(observation_obligation)
    policy = OrchestrationPolicy(max_route_length=1)
    initial = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[objective], registry=registry,
        profiles=catalog, budget=AuditBudget(6, 2), policy=policy,
    )
    result = run_adaptive_orchestration(
        initial_plan=initial,
        obligations={observation_obligation.obligation_id: observation_obligation},
        analysis_results={orchestration_result.analysis_id: orchestration_result},
        verification_service=VerificationService(registry),
        registry=registry, profiles=catalog, orchestration_policy=policy,
        adaptive_policy=AdaptiveReplanningPolicy(replan_on_failed=True),
    )
    assert result.status is AdaptiveSessionStatus.SATISFIED
    assert len(result.executions) == 2


def test_adaptive_session_identity_is_deterministic(observation_obligation, orchestration_result):
    registry = VerifierRegistry(); registry.register(CheapInconclusiveVerifier()); registry.register(ExpensiveConfirmVerifier())
    catalog = _catalog(_profile("cheap-inconclusive", 1), _profile("expensive-confirm", 5))
    objective = _objective(observation_obligation)
    policy = OrchestrationPolicy(max_route_length=1)
    initial = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[objective], registry=registry,
        profiles=catalog, budget=AuditBudget(6, 2), policy=policy,
    )
    kwargs = dict(
        initial_plan=initial,
        obligations={observation_obligation.obligation_id: observation_obligation},
        analysis_results={orchestration_result.analysis_id: orchestration_result},
        verification_service=VerificationService(registry),
        registry=registry, profiles=catalog, orchestration_policy=policy,
    )
    assert run_adaptive_orchestration(**kwargs).session_id == run_adaptive_orchestration(**kwargs).session_id


def test_adaptive_session_has_no_finding_or_memory_fields(observation_obligation, orchestration_result):
    registry = VerifierRegistry(); registry.register(CheapConfirmVerifier())
    catalog = _catalog(_profile("cheap-confirm", 1))
    objective = _objective(observation_obligation)
    initial = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[objective], registry=registry,
        profiles=catalog, budget=AuditBudget(2, 1), policy=OrchestrationPolicy(max_route_length=1),
    )
    result = run_adaptive_orchestration(
        initial_plan=initial,
        obligations={observation_obligation.obligation_id: observation_obligation},
        analysis_results={orchestration_result.analysis_id: orchestration_result},
        verification_service=VerificationService(registry), registry=registry, profiles=catalog,
        orchestration_policy=OrchestrationPolicy(max_route_length=1),
    )
    payload = result.to_dict()
    assert "findings" not in payload
    assert "memory" not in payload
    assert "promotions" not in payload
