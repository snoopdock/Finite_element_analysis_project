from audit_engine.semantic_audit.graph.analysis import VerificationStatus
from audit_engine.semantic_audit.orchestration import (
    AuditBudget,
    ExecutionMode,
    OperationalPriority,
    OrchestrationPolicy,
    RoutePlanningStatus,
    VerificationMethod,
    VerificationObjective,
    VerifierOrchestrationProfile,
    VerifierProfileCatalog,
    build_orchestration_plan,
)
from audit_engine.semantic_audit.verification import VerifierRegistry

from .conftest import CheapConfirmVerifier, CheapInconclusiveVerifier, ExpensiveConfirmVerifier


def _catalog(*profiles):
    result = VerifierProfileCatalog()
    for profile in profiles:
        result.register(profile)
    return result


def _profile(verifier_id, cost, *, state=VerificationStatus.VALIDATED, side_effect_free=True,
             mode=ExecutionMode.IN_PROCESS_READ_ONLY):
    return VerifierOrchestrationProfile(
        verifier_id, "1.0.0", VerificationMethod.CONTRACT, cost, state,
        execution_mode=mode, side_effect_free=side_effect_free,
    )


def test_planner_chooses_lowest_cost_sufficient_verifier(observation_obligation):
    registry = VerifierRegistry()
    registry.register(ExpensiveConfirmVerifier())
    registry.register(CheapConfirmVerifier())
    catalog = _catalog(_profile("expensive-confirm", 5), _profile("cheap-confirm", 1))
    objective = VerificationObjective.create(
        obligation_id=observation_obligation.obligation_id,
        minimum_evidence_state=VerificationStatus.VALIDATED,
    )
    plan = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[objective], registry=registry,
        profiles=catalog, budget=AuditBudget(1, 1),
    )
    assert plan.routes[0].actions[0].verifier_id == "cheap-confirm"


def test_planner_reserves_fallback_when_budget_allows(observation_obligation, fallback_registry):
    catalog = _catalog(_profile("cheap-inconclusive", 1), _profile("expensive-confirm", 5))
    objective = VerificationObjective.create(
        obligation_id=observation_obligation.obligation_id,
        minimum_evidence_state=VerificationStatus.VALIDATED,
    )
    plan = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[objective], registry=fallback_registry,
        profiles=catalog, budget=AuditBudget(6, 2),
    )
    assert [a.verifier_id for a in plan.routes[0].actions] == [
        "cheap-inconclusive", "expensive-confirm"
    ]
    assert plan.reserved_cost_units == 6


def test_planner_never_exceeds_hard_budget(observation_obligation, fallback_registry):
    catalog = _catalog(_profile("cheap-inconclusive", 1), _profile("expensive-confirm", 5))
    objective = VerificationObjective.create(
        obligation_id=observation_obligation.obligation_id,
        minimum_evidence_state=VerificationStatus.VALIDATED,
    )
    plan = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[objective], registry=fallback_registry,
        profiles=catalog, budget=AuditBudget(1, 1),
    )
    assert len(plan.routes[0].actions) == 1
    assert plan.reserved_cost_units <= 1


def test_planner_marks_unscheduled_budget_explicitly(observation_obligation):
    registry = VerifierRegistry()
    registry.register(ExpensiveConfirmVerifier())
    catalog = _catalog(_profile("expensive-confirm", 5))
    objective = VerificationObjective.create(
        obligation_id=observation_obligation.obligation_id,
        minimum_evidence_state=VerificationStatus.VALIDATED,
    )
    plan = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[objective], registry=registry,
        profiles=catalog, budget=AuditBudget(1, 1),
    )
    assert plan.routes[0].status is RoutePlanningStatus.UNSCHEDULED_BUDGET


def test_validated_objective_rejects_corroboration_only_ceiling(observation_obligation):
    registry = VerifierRegistry()
    registry.register(CheapConfirmVerifier())
    catalog = _catalog(_profile("cheap-confirm", 1, state=VerificationStatus.CORROBORATED))
    objective = VerificationObjective.create(
        obligation_id=observation_obligation.obligation_id,
        minimum_evidence_state=VerificationStatus.VALIDATED,
    )
    plan = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[objective], registry=registry,
        profiles=catalog, budget=AuditBudget(3, 2),
    )
    assert plan.routes[0].status is RoutePlanningStatus.UNSCHEDULED_POLICY


def test_side_effecting_verifier_rejected_by_default_policy(observation_obligation):
    registry = VerifierRegistry()
    registry.register(CheapConfirmVerifier())
    catalog = _catalog(_profile("cheap-confirm", 1, side_effect_free=False))
    objective = VerificationObjective.create(
        obligation_id=observation_obligation.obligation_id,
        minimum_evidence_state=VerificationStatus.VALIDATED,
    )
    plan = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[objective], registry=registry,
        profiles=catalog, budget=AuditBudget(3, 2),
    )
    assert plan.routes[0].status is RoutePlanningStatus.UNSCHEDULED_POLICY


def test_execution_mode_requires_explicit_budget_permission(observation_obligation):
    registry = VerifierRegistry()
    registry.register(CheapConfirmVerifier())
    catalog = _catalog(_profile("cheap-confirm", 1, mode=ExecutionMode.SANDBOXED))
    objective = VerificationObjective.create(
        obligation_id=observation_obligation.obligation_id,
        minimum_evidence_state=VerificationStatus.VALIDATED,
    )
    denied = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[objective], registry=registry,
        profiles=catalog, budget=AuditBudget(3, 2),
    )
    assert denied.routes[0].status is RoutePlanningStatus.UNSCHEDULED_POLICY
    allowed = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[objective], registry=registry,
        profiles=catalog,
        budget=AuditBudget(3, 2, (ExecutionMode.IN_PROCESS_READ_ONLY, ExecutionMode.SANDBOXED)),
    )
    assert allowed.routes[0].status is RoutePlanningStatus.SCHEDULED


def test_high_priority_objective_gets_scarce_budget_first(observation_obligation):
    registry = VerifierRegistry()
    registry.register(CheapConfirmVerifier())
    catalog = _catalog(_profile("cheap-confirm", 1))
    high = VerificationObjective.create(
        obligation_id=observation_obligation.obligation_id,
        minimum_evidence_state=VerificationStatus.VALIDATED,
        priority=OperationalPriority.HIGH,
    )
    low = VerificationObjective.create(
        obligation_id=observation_obligation.obligation_id,
        minimum_evidence_state=VerificationStatus.VALIDATED,
        priority=OperationalPriority.LOW,
        excluded_verifier_ids=(),
    )
    # Distinguish objective identity while preserving obligation by allowing same verifier list.
    low = VerificationObjective.create(
        obligation_id=observation_obligation.obligation_id,
        minimum_evidence_state=VerificationStatus.OBSERVED,
        priority=OperationalPriority.LOW,
    )
    plan = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[low, high], registry=registry,
        profiles=catalog, budget=AuditBudget(1, 1),
    )
    assert plan.routes[0].objective.priority is OperationalPriority.HIGH
    assert plan.routes[0].status is RoutePlanningStatus.SCHEDULED
    assert plan.routes[1].status is RoutePlanningStatus.UNSCHEDULED_BUDGET


def test_planner_is_deterministic(observation_obligation, fallback_registry):
    catalog = _catalog(_profile("cheap-inconclusive", 1), _profile("expensive-confirm", 5))
    objective = VerificationObjective.create(
        obligation_id=observation_obligation.obligation_id,
        minimum_evidence_state=VerificationStatus.VALIDATED,
    )
    kwargs = dict(
        obligations=[observation_obligation], objectives=[objective], registry=fallback_registry,
        profiles=catalog, budget=AuditBudget(6, 2),
    )
    assert build_orchestration_plan(**kwargs).plan_id == build_orchestration_plan(**kwargs).plan_id

def test_unprofiled_verifier_is_not_given_implicit_cost(observation_obligation):
    registry = VerifierRegistry(); registry.register(CheapConfirmVerifier())
    catalog = VerifierProfileCatalog()
    objective = VerificationObjective.create(
        obligation_id=observation_obligation.obligation_id,
        minimum_evidence_state=VerificationStatus.VALIDATED,
    )
    plan = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[objective], registry=registry,
        profiles=catalog, budget=AuditBudget(10, 10),
    )
    assert plan.routes[0].status is RoutePlanningStatus.UNSCHEDULED_POLICY
    assert plan.routes[0].actions == ()


def test_max_route_length_bounds_fallback_reservation(observation_obligation, fallback_registry):
    catalog = _catalog(_profile("cheap-inconclusive", 1), _profile("expensive-confirm", 5))
    objective = VerificationObjective.create(
        obligation_id=observation_obligation.obligation_id,
        minimum_evidence_state=VerificationStatus.VALIDATED,
    )
    plan = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[objective], registry=fallback_registry,
        profiles=catalog, budget=AuditBudget(10, 10),
        policy=OrchestrationPolicy(max_route_length=1),
    )
    assert len(plan.routes[0].actions) == 1


def test_primary_coverage_is_reserved_before_fallbacks(observation_obligation, fallback_registry):
    catalog = _catalog(_profile("cheap-inconclusive", 1), _profile("expensive-confirm", 5))
    high = VerificationObjective.create(
        obligation_id=observation_obligation.obligation_id,
        minimum_evidence_state=VerificationStatus.VALIDATED,
        priority=OperationalPriority.HIGH,
    )
    low = VerificationObjective.create(
        obligation_id=observation_obligation.obligation_id,
        minimum_evidence_state=VerificationStatus.OBSERVED,
        priority=OperationalPriority.LOW,
    )
    plan = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[high, low], registry=fallback_registry,
        profiles=catalog, budget=AuditBudget(2, 2),
    )
    assert all(route.status is RoutePlanningStatus.SCHEDULED for route in plan.routes)
    assert [len(route.actions) for route in plan.routes] == [1, 1]
