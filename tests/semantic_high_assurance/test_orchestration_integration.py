from __future__ import annotations

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.high_assurance import register_builtin_high_assurance_verifiers
from audit_engine.semantic_audit.orchestration import (
    AuditBudget,
    OrchestrationPolicy,
    VerificationMethod,
    VerificationObjective,
    build_orchestration_plan,
    builtin_profile_catalog,
)
from audit_engine.semantic_audit.verification import VerifierRegistry

from .conftest import digest_obligation, static_import_obligation


def registry_and_profiles():
    registry = VerifierRegistry(); register_builtin_high_assurance_verifiers(registry)
    return registry, builtin_profile_catalog()


def test_builtin_catalog_profiles_static_high_assurance_verifier():
    _, profiles = registry_and_profiles()
    profile = profiles.get("python-static-import")
    assert profile is not None
    assert profile.method is VerificationMethod.STATIC_ANALYSIS
    assert profile.cost_units == 4
    assert profile.maximum_evidence_state is VerificationStatus.VALIDATED


def test_builtin_catalog_profiles_integrity_verifier():
    _, profiles = registry_and_profiles()
    profile = profiles.get("artifact-digest-integrity")
    assert profile.method is VerificationMethod.ARTIFACT_INTEGRITY
    assert profile.cost_units == 2


def test_planner_can_schedule_requested_static_high_assurance_verifier(analysis_result):
    registry, profiles = registry_and_profiles()
    obligation = static_import_obligation(analysis_result, "import os\n")
    objective = VerificationObjective.create(
        obligation_id=obligation.obligation_id,
        minimum_evidence_state=VerificationStatus.VALIDATED,
    )
    plan = build_orchestration_plan(
        obligations=(obligation,), objectives=(objective,), registry=registry,
        profiles=profiles, budget=AuditBudget(4, 1), policy=OrchestrationPolicy(max_route_length=1),
    )
    assert plan.routes[0].actions[0].verifier_id == "python-static-import"


def test_planner_does_not_schedule_static_verifier_when_budget_too_small(analysis_result):
    registry, profiles = registry_and_profiles()
    obligation = static_import_obligation(analysis_result, "import os\n")
    objective = VerificationObjective.create(
        obligation_id=obligation.obligation_id,
        minimum_evidence_state=VerificationStatus.VALIDATED,
    )
    plan = build_orchestration_plan(
        obligations=(obligation,), objectives=(objective,), registry=registry,
        profiles=profiles, budget=AuditBudget(3, 1), policy=OrchestrationPolicy(max_route_length=1),
    )
    assert plan.routes[0].status.value == "unscheduled_budget"


def test_integrity_verifier_uses_separate_method_class(analysis_result):
    registry, profiles = registry_and_profiles()
    obligation = digest_obligation(analysis_result, "artifact")
    objective = VerificationObjective.create(
        obligation_id=obligation.obligation_id,
        minimum_evidence_state=VerificationStatus.VALIDATED,
    )
    plan = build_orchestration_plan(
        obligations=(obligation,), objectives=(objective,), registry=registry,
        profiles=profiles, budget=AuditBudget(2, 1), policy=OrchestrationPolicy(max_route_length=1),
    )
    assert plan.routes[0].actions[0].method.value == "artifact_integrity"
