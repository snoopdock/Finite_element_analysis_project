import pytest

from audit_engine.semantic_audit.graph.analysis import VerificationStatus
from audit_engine.semantic_audit.orchestration import (
    AdaptiveReplanningPolicy,
    AuditBudget,
    OrchestrationPolicy,
    RemainingAuditBudget,
    ReplanningDisposition,
    VerificationMethod,
    VerificationObjective,
    VerifierOrchestrationProfile,
    VerifierProfileCatalog,
    build_adaptive_replan,
    build_orchestration_plan,
    execute_orchestration_plan,
)
from audit_engine.semantic_audit.verification import VerificationService, VerifierRegistry

from .conftest import CheapConfirmVerifier, CheapInconclusiveVerifier, ErrorVerifier, ExpensiveConfirmVerifier


def _profile(verifier_id, cost):
    return VerifierOrchestrationProfile(
        verifier_id,
        "1.0.0",
        VerificationMethod.CONTRACT,
        cost,
        VerificationStatus.VALIDATED,
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


def _initial_exhausted(observation_obligation, orchestration_result):
    registry = VerifierRegistry()
    registry.register(CheapInconclusiveVerifier())
    registry.register(ExpensiveConfirmVerifier())
    catalog = _catalog(_profile("cheap-inconclusive", 1), _profile("expensive-confirm", 5))
    objective = _objective(observation_obligation)
    policy = OrchestrationPolicy(max_route_length=1)
    plan = build_orchestration_plan(
        obligations=[observation_obligation],
        objectives=[objective],
        registry=registry,
        profiles=catalog,
        budget=AuditBudget(6, 2),
        policy=policy,
    )
    execution = execute_orchestration_plan(
        plan=plan,
        obligations={observation_obligation.obligation_id: observation_obligation},
        analysis_results={orchestration_result.analysis_id: orchestration_result},
        verification_service=VerificationService(registry),
        policy=policy,
    )
    return registry, catalog, objective, policy, plan, execution


def test_replan_selects_unattempted_verifier_after_exhaustion(observation_obligation, orchestration_result):
    registry, catalog, objective, policy, plan, execution = _initial_exhausted(
        observation_obligation, orchestration_result
    )
    remaining = RemainingAuditBudget.from_consumption(
        plan.budget,
        consumed_cost_units=execution.consumed_cost_units,
        consumed_verifier_runs=execution.consumed_verifier_runs,
    )
    replan = build_adaptive_replan(
        source_plan=plan,
        source_execution=execution,
        obligations={observation_obligation.obligation_id: observation_obligation},
        registry=registry,
        profiles=catalog,
        remaining_budget=remaining,
        cumulative_attempted_verifiers={objective.objective_id: {"cheap-inconclusive"}},
        round_index=1,
        orchestration_policy=policy,
    )
    assert replan.continuation_plan is not None
    assert replan.continuation_plan.routes[0].actions[0].verifier_id == "expensive-confirm"
    decision = replan.decisions[0]
    assert decision.disposition is ReplanningDisposition.REPLAN_SCHEDULED
    assert decision.attempted_verifier_ids == ("cheap-inconclusive",)


def test_replan_never_repeats_attempted_verifier_by_default(observation_obligation, orchestration_result):
    registry, catalog, objective, policy, plan, execution = _initial_exhausted(
        observation_obligation, orchestration_result
    )
    remaining = RemainingAuditBudget.from_consumption(
        plan.budget,
        consumed_cost_units=1,
        consumed_verifier_runs=1,
    )
    replan = build_adaptive_replan(
        source_plan=plan,
        source_execution=execution,
        obligations={observation_obligation.obligation_id: observation_obligation},
        registry=registry,
        profiles=catalog,
        remaining_budget=remaining,
        cumulative_attempted_verifiers={objective.objective_id: {"cheap-inconclusive", "expensive-confirm"}},
        round_index=1,
        orchestration_policy=policy,
    )
    assert replan.continuation_plan is None
    assert replan.decisions[0].disposition is ReplanningDisposition.NO_REPLAN_CAPABILITY


def test_replan_stops_when_remaining_budget_is_zero(observation_obligation, orchestration_result):
    registry, catalog, objective, policy, plan, execution = _initial_exhausted(
        observation_obligation, orchestration_result
    )
    remaining = RemainingAuditBudget(0, 1, plan.budget.allowed_execution_modes)
    replan = build_adaptive_replan(
        source_plan=plan,
        source_execution=execution,
        obligations={observation_obligation.obligation_id: observation_obligation},
        registry=registry,
        profiles=catalog,
        remaining_budget=remaining,
        cumulative_attempted_verifiers={objective.objective_id: {"cheap-inconclusive"}},
        round_index=1,
        orchestration_policy=policy,
    )
    assert replan.continuation_plan is None
    assert replan.decisions[0].disposition is ReplanningDisposition.NO_REPLAN_BUDGET


def test_satisfied_objective_is_never_replanned(observation_obligation, orchestration_result):
    registry = VerifierRegistry(); registry.register(CheapConfirmVerifier())
    catalog = _catalog(_profile("cheap-confirm", 1))
    objective = _objective(observation_obligation)
    policy = OrchestrationPolicy(max_route_length=1)
    plan = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[objective], registry=registry,
        profiles=catalog, budget=AuditBudget(3, 2), policy=policy,
    )
    execution = execute_orchestration_plan(
        plan=plan,
        obligations={observation_obligation.obligation_id: observation_obligation},
        analysis_results={orchestration_result.analysis_id: orchestration_result},
        verification_service=VerificationService(registry),
        policy=policy,
    )
    remaining = RemainingAuditBudget.from_consumption(
        plan.budget,
        consumed_cost_units=execution.consumed_cost_units,
        consumed_verifier_runs=execution.consumed_verifier_runs,
    )
    replan = build_adaptive_replan(
        source_plan=plan, source_execution=execution,
        obligations={observation_obligation.obligation_id: observation_obligation},
        registry=registry, profiles=catalog, remaining_budget=remaining,
        cumulative_attempted_verifiers={objective.objective_id: {"cheap-confirm"}},
        round_index=1, orchestration_policy=policy,
    )
    assert replan.continuation_plan is None
    assert replan.decisions[0].disposition is ReplanningDisposition.NO_REPLAN_SATISFIED


def test_failure_requires_explicit_adaptive_policy(observation_obligation, orchestration_result):
    registry = VerifierRegistry(); registry.register(ErrorVerifier()); registry.register(ExpensiveConfirmVerifier())
    catalog = _catalog(_profile("error-verifier", 1), _profile("expensive-confirm", 5))
    objective = _objective(observation_obligation)
    policy = OrchestrationPolicy(max_route_length=1)
    plan = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[objective], registry=registry,
        profiles=catalog, budget=AuditBudget(6, 2), policy=policy,
    )
    execution = execute_orchestration_plan(
        plan=plan,
        obligations={observation_obligation.obligation_id: observation_obligation},
        analysis_results={orchestration_result.analysis_id: orchestration_result},
        verification_service=VerificationService(registry), policy=policy,
    )
    remaining = RemainingAuditBudget.from_consumption(
        plan.budget,
        consumed_cost_units=execution.consumed_cost_units,
        consumed_verifier_runs=execution.consumed_verifier_runs,
    )
    default = build_adaptive_replan(
        source_plan=plan, source_execution=execution,
        obligations={observation_obligation.obligation_id: observation_obligation},
        registry=registry, profiles=catalog, remaining_budget=remaining,
        cumulative_attempted_verifiers={objective.objective_id: {"error-verifier"}},
        round_index=1, orchestration_policy=policy,
    )
    assert default.decisions[0].disposition is ReplanningDisposition.NO_REPLAN_POLICY

    allowed = build_adaptive_replan(
        source_plan=plan, source_execution=execution,
        obligations={observation_obligation.obligation_id: observation_obligation},
        registry=registry, profiles=catalog, remaining_budget=remaining,
        cumulative_attempted_verifiers={objective.objective_id: {"error-verifier"}},
        round_index=1, orchestration_policy=policy,
        adaptive_policy=AdaptiveReplanningPolicy(replan_on_failed=True),
    )
    assert allowed.continuation_plan is not None
    assert allowed.continuation_plan.routes[0].actions[0].verifier_id == "expensive-confirm"


def test_round_limit_is_explicit(observation_obligation, orchestration_result):
    registry, catalog, objective, policy, plan, execution = _initial_exhausted(
        observation_obligation, orchestration_result
    )
    remaining = RemainingAuditBudget.from_consumption(
        plan.budget,
        consumed_cost_units=execution.consumed_cost_units,
        consumed_verifier_runs=execution.consumed_verifier_runs,
    )
    replan = build_adaptive_replan(
        source_plan=plan, source_execution=execution,
        obligations={observation_obligation.obligation_id: observation_obligation},
        registry=registry, profiles=catalog, remaining_budget=remaining,
        cumulative_attempted_verifiers={objective.objective_id: {"cheap-inconclusive"}},
        round_index=2, orchestration_policy=policy,
        adaptive_policy=AdaptiveReplanningPolicy(max_replanning_rounds=1),
    )
    assert replan.continuation_plan is None
    assert replan.decisions[0].disposition is ReplanningDisposition.NO_REPLAN_ROUND_LIMIT


def test_replan_identity_is_deterministic(observation_obligation, orchestration_result):
    registry, catalog, objective, policy, plan, execution = _initial_exhausted(
        observation_obligation, orchestration_result
    )
    remaining = RemainingAuditBudget.from_consumption(
        plan.budget,
        consumed_cost_units=1,
        consumed_verifier_runs=1,
    )
    kwargs = dict(
        source_plan=plan, source_execution=execution,
        obligations={observation_obligation.obligation_id: observation_obligation},
        registry=registry, profiles=catalog, remaining_budget=remaining,
        cumulative_attempted_verifiers={objective.objective_id: {"cheap-inconclusive"}},
        round_index=1, orchestration_policy=policy,
    )
    assert build_adaptive_replan(**kwargs).replan_id == build_adaptive_replan(**kwargs).replan_id


def test_remaining_budget_rejects_overconsumption():
    budget = AuditBudget(3, 2)
    with pytest.raises(ValueError):
        RemainingAuditBudget.from_consumption(budget, consumed_cost_units=4, consumed_verifier_runs=1)
    with pytest.raises(ValueError):
        RemainingAuditBudget.from_consumption(budget, consumed_cost_units=1, consumed_verifier_runs=3)
