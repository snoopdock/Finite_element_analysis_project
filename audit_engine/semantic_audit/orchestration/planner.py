"""Deterministic budget-aware planner for verification objectives."""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable, Mapping

from audit_engine.semantic_audit.graph.analysis.identity import deterministic_id
from audit_engine.semantic_audit.verification.models import VerificationObligation
from audit_engine.semantic_audit.verification.registry import VerifierRegistry

from .models import (
    AuditBudget,
    OrchestrationPlan,
    PlannedVerifierAction,
    RoutePlanningStatus,
    VerificationObjective,
    VerificationRoute,
    priority_sort_key,
)
from .policy import OrchestrationPolicy, evidence_rank
from .profiles import VerifierProfileCatalog


def eligible_profiles(
    *,
    objective: VerificationObjective,
    obligation: VerificationObligation,
    registry: VerifierRegistry,
    profiles: VerifierProfileCatalog,
    budget: AuditBudget,
    policy: OrchestrationPolicy,
    extra_excluded_verifier_ids: frozenset[str] = frozenset(),
):
    compatible = registry.compatible(obligation)
    result = []
    for verifier in compatible:
        verifier_id = verifier.descriptor.verifier_id
        if objective.allowed_verifier_ids and verifier_id not in objective.allowed_verifier_ids:
            continue
        if verifier_id in objective.excluded_verifier_ids or verifier_id in extra_excluded_verifier_ids:
            continue
        profile = profiles.get(verifier_id)
        if profile is None:
            continue
        if profile.verifier_version != verifier.descriptor.version:
            continue
        if profile.method not in policy.allowed_methods:
            continue
        if profile.execution_mode not in budget.allowed_execution_modes:
            continue
        if policy.require_side_effect_free and not profile.side_effect_free:
            continue
        if evidence_rank(profile.maximum_evidence_state) < evidence_rank(objective.minimum_evidence_state):
            continue
        result.append(profile)
    result.sort(key=lambda p: (p.cost_units, p.verifier_id, p.verifier_version))
    return result


def build_orchestration_plan(
    *,
    obligations: Iterable[VerificationObligation],
    objectives: Iterable[VerificationObjective],
    registry: VerifierRegistry,
    profiles: VerifierProfileCatalog,
    budget: AuditBudget,
    policy: OrchestrationPolicy | None = None,
) -> OrchestrationPlan:
    policy = policy or OrchestrationPolicy()
    obligation_by_id = {item.obligation_id: item for item in obligations}
    objectives = tuple(objectives)
    if len({item.objective_id for item in objectives}) != len(objectives):
        raise ValueError("Duplicate objective IDs are not allowed.")
    for objective in objectives:
        if objective.obligation_id not in obligation_by_id:
            raise ValueError(f"Unknown obligation for objective: {objective.obligation_id}")

    profiles.validate_against_registry(registry)
    ordered = sorted(objectives, key=priority_sort_key)

    # First pass reserves one least-cost sufficient verifier per objective. This
    # avoids consuming the entire budget on fallbacks for the first objective.
    mutable: dict[str, dict] = {}
    used_cost = 0
    used_runs = 0
    for objective in ordered:
        obligation = obligation_by_id[objective.obligation_id]
        candidates = eligible_profiles(
            objective=objective,
            obligation=obligation,
            registry=registry,
            profiles=profiles,
            budget=budget,
            policy=policy,
        )
        if not candidates:
            compatible = registry.compatible(obligation)
            status = (
                RoutePlanningStatus.UNSCHEDULED_NO_CAPABILITY
                if not compatible
                else RoutePlanningStatus.UNSCHEDULED_POLICY
            )
            mutable[objective.objective_id] = {
                "objective": objective,
                "status": status,
                "actions": [],
                "reason": "no_eligible_verifier_profile",
                "candidates": candidates,
            }
            continue
        primary = candidates[0]
        if (
            used_cost + primary.cost_units > budget.total_cost_units
            or used_runs + 1 > budget.max_verifier_runs
        ):
            mutable[objective.objective_id] = {
                "objective": objective,
                "status": RoutePlanningStatus.UNSCHEDULED_BUDGET,
                "actions": [],
                "reason": "insufficient_budget_for_primary_verifier",
                "candidates": candidates,
            }
            continue
        action = PlannedVerifierAction.from_profile(objective.objective_id, primary)
        used_cost += primary.cost_units
        used_runs += 1
        mutable[objective.objective_id] = {
            "objective": objective,
            "status": RoutePlanningStatus.SCHEDULED,
            "actions": [action],
            "reason": None,
            "candidates": candidates,
        }

    # Second pass reserves bounded fallbacks from remaining budget.
    for objective in ordered:
        entry = mutable[objective.objective_id]
        if entry["status"] is not RoutePlanningStatus.SCHEDULED:
            continue
        selected_ids = {item.verifier_id for item in entry["actions"]}
        for profile in entry["candidates"]:
            if profile.verifier_id in selected_ids:
                continue
            if len(entry["actions"]) >= policy.max_route_length:
                break
            if used_cost + profile.cost_units > budget.total_cost_units:
                continue
            if used_runs + 1 > budget.max_verifier_runs:
                break
            entry["actions"].append(PlannedVerifierAction.from_profile(objective.objective_id, profile))
            selected_ids.add(profile.verifier_id)
            used_cost += profile.cost_units
            used_runs += 1

    routes = tuple(
        VerificationRoute(
            objective=mutable[obj.objective_id]["objective"],
            status=mutable[obj.objective_id]["status"],
            actions=tuple(mutable[obj.objective_id]["actions"]),
            reason=mutable[obj.objective_id]["reason"],
        )
        for obj in ordered
    )
    identity = {
        "policy_version": policy.version,
        "budget": budget.to_dict(),
        "routes": [route.to_dict() for route in routes],
    }
    plan = OrchestrationPlan(
        plan_id=deterministic_id("audit-orchestration-plan", identity, length=28),
        policy_version=policy.version,
        budget=budget,
        routes=routes,
    )
    if plan.reserved_cost_units > budget.total_cost_units:
        raise AssertionError("Planner exceeded cost budget.")
    if plan.reserved_verifier_runs > budget.max_verifier_runs:
        raise AssertionError("Planner exceeded verifier-run budget.")
    return plan
