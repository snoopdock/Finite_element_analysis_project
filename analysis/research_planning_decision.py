#!/usr/bin/env python3
"""Evaluate R8 ResearchPlanningSignal objects into bounded planning decisions.

This module implements the R8.3 planning boundary only. It is deliberately
pure and deterministic: no retrieval, network, LLM, lifecycle, or scientific
state mutation is performed here.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping, Sequence

from analysis.retrieval_attention_planning_signal import (
    ALLOWED_CONDITIONS,
    validate_research_planning_signal,
)


PLANNING_DECISION_SCHEMA_VERSION = 1
PLANNER_VERSION = "r8.4-v1"

ALLOWED_DECISION_TYPES = {
    "no_action",
    "defer",
    "prioritize_research",
    "formulate_acquisition_request",
}

# The evaluator accepts only a small, process-level planning context. This is
# intentionally separate from ResearchPlanningSignal, whose R8.2 vocabulary
# remains unchanged. Unknown context keys are rejected rather than inferred.
ALLOWED_CONTEXT_FIELDS = {
    "active_query_scopes",
    "alternative_providers",
    "deferred_signal_ids",
}


def _require_non_empty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        raise ValueError(f"{field} must be a list-like collection")
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = _require_non_empty_string(item, field)
        if normalized in seen:
            raise ValueError(f"{field} must not contain duplicates")
        seen.add(normalized)
        result.append(normalized)
    return result


def _validate_context(context: Mapping[str, Any] | None) -> dict[str, list[str]]:
    if context is None:
        return {
            "active_query_scopes": [],
            "alternative_providers": [],
            "deferred_signal_ids": [],
        }
    if not isinstance(context, Mapping):
        raise TypeError("planning_context must be a mapping")
    unknown = sorted(set(context) - ALLOWED_CONTEXT_FIELDS)
    if unknown:
        raise ValueError(f"unknown planning_context fields: {unknown}")

    return {
        "active_query_scopes": _string_list(
            context.get("active_query_scopes", []),
            "planning_context.active_query_scopes",
        ),
        "alternative_providers": _string_list(
            context.get("alternative_providers", []),
            "planning_context.alternative_providers",
        ),
        "deferred_signal_ids": _string_list(
            context.get("deferred_signal_ids", []),
            "planning_context.deferred_signal_ids",
        ),
    }


def _target(signal: Mapping[str, Any]) -> dict[str, str]:
    target = signal.get("target")
    if not isinstance(target, Mapping):
        raise ValueError("ResearchPlanningSignal.target must be a mapping")

    result: dict[str, str] = {}
    for field in ("query_scope", "provider"):
        if field in target and target[field] is not None:
            result[field] = _require_non_empty_string(
                target[field], f"target.{field}"
            )
    return result


def _condition(signal: Mapping[str, Any]) -> str:
    operational = signal.get("operational_condition")
    if not isinstance(operational, Mapping):
        raise ValueError(
            "ResearchPlanningSignal.operational_condition is required for R8.4"
        )
    condition = _require_non_empty_string(
        operational.get("observed_condition"),
        "operational_condition.observed_condition",
    )
    if condition not in ALLOWED_CONDITIONS:
        raise ValueError(f"unsupported observed_condition: {condition!r}")
    return condition


def _decision_id(
    decision_type: str,
    signal_ids: Sequence[str],
    rationale: str,
    target: Mapping[str, Any] | None,
    priority: float | None,
) -> str:
    payload = {
        "planner_version": PLANNER_VERSION,
        "schema_version": PLANNING_DECISION_SCHEMA_VERSION,
        "decision_type": decision_type,
        "input_signal_ids": list(signal_ids),
        "rationale": rationale,
        "target": dict(target) if target is not None else None,
        "priority": priority,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return f"planning-decision-{hashlib.sha256(encoded).hexdigest()[:24]}"


def _priority_for(condition: str, has_alternative: bool) -> float:
    # Priority is deliberately a process score. It does not represent
    # scientific importance, evidence strength, or claim rank.
    if condition == "repeated_query_provider_non_success":
        return 0.95 if has_alternative else 0.85
    if condition == "provider_unavailable":
        return 0.90 if has_alternative else 0.75
    if condition == "provider_partially_available":
        return 0.65
    if condition == "repeated_query_provider_empty_result":
        return 0.35
    return 0.20


def _evaluate_one(
    signal: Mapping[str, Any],
    context: Mapping[str, list[str]],
) -> dict[str, Any]:
    normalized = validate_research_planning_signal(signal)
    signal_id = _require_non_empty_string(
        normalized["research_planning_signal_id"],
        "research_planning_signal_id",
    )
    target = _target(normalized)
    condition = _condition(normalized)
    query_scope = target.get("query_scope")
    provider = target.get("provider")

    if signal_id in context["deferred_signal_ids"]:
        decision_type = "defer"
        rationale = "The planning context explicitly defers this signal."
        priority = 0.25
    elif (
        context["active_query_scopes"]
        and query_scope
        and query_scope not in context["active_query_scopes"]
    ):
        decision_type = "defer"
        rationale = "The signal is outside the currently active query scope."
        priority = 0.20
    elif condition in {
        "provider_unavailable",
        "repeated_query_provider_non_success",
    }:
        alternatives = set(context["alternative_providers"])
        has_alternative = bool(alternatives - ({provider} if provider else set()))
        if has_alternative:
            decision_type = "formulate_acquisition_request"
            rationale = (
                "The acquisition provider is operationally unavailable and an "
                "already-defined alternative provider is available."
            )
        else:
            decision_type = "prioritize_research"
            rationale = (
                "The acquisition provider is operationally unavailable; research "
                "process attention is warranted without inferring evidence weakness."
            )
        priority = _priority_for(condition, has_alternative)
    elif condition == "provider_partially_available":
        decision_type = "prioritize_research"
        rationale = (
            "The acquisition provider is only partially available; process priority "
            "may increase without changing scientific state."
        )
        priority = _priority_for(condition, False)
    elif condition in {
        "query_returned_empty_result",
        "repeated_query_provider_empty_result",
    }:
        # Empty retrieval results are explicitly not treated as absence of
        # literature. Without an independent planning reason, no action is the
        # conservative result; the signal remains traceable as an input.
        decision_type = "no_action"
        rationale = (
            "An empty retrieval result does not by itself establish literature "
            "absence or an evidence gap, so no additional planning response is warranted."
        )
        priority = _priority_for(condition, False)
    else:  # defensive: _condition already validates the vocabulary
        raise ValueError(f"unsupported observed_condition: {condition!r}")

    decision_target = {}
    if query_scope:
        decision_target["query_scope"] = query_scope
    if provider:
        decision_target["provider"] = provider

    decision = {
        "research_planning_decision_id": _decision_id(
            decision_type,
            [signal_id],
            rationale,
            decision_target or None,
            priority,
        ),
        "decision_type": decision_type,
        "input_signal_ids": [signal_id],
        "rationale": rationale,
        "target": decision_target,
        "priority": priority,
        "planner_version": PLANNER_VERSION,
    }
    validate_research_planning_decision(decision)
    return decision


def evaluate_research_planning_signal(
    signal: Mapping[str, Any],
    *,
    planning_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate one planning signal without side effects."""
    context = _validate_context(planning_context)
    return _evaluate_one(signal, context)


def evaluate_research_planning_signals(
    signals: Sequence[Mapping[str, Any]],
    *,
    planning_context: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Evaluate signals independently and return deterministic ID ordering."""
    if not isinstance(signals, (list, tuple)):
        raise TypeError("signals must be a list or tuple")
    context = _validate_context(planning_context)
    decisions = [_evaluate_one(signal, context) for signal in signals]
    decisions.sort(key=lambda item: item["research_planning_decision_id"])
    return decisions


def validate_research_planning_decision(
    decision: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate an R8.3 ResearchPlanningDecision and return a defensive copy."""
    if not isinstance(decision, Mapping):
        raise TypeError("research planning decision must be a mapping")

    allowed_fields = {
        "research_planning_decision_id",
        "decision_type",
        "input_signal_ids",
        "rationale",
        "target",
        "priority",
        "created_at",
        "planner_version",
        "acquisition_request_reference",
    }
    unknown = sorted(set(decision) - allowed_fields)
    if unknown:
        raise ValueError(f"unknown ResearchPlanningDecision fields: {unknown}")

    required = {
        "research_planning_decision_id",
        "decision_type",
        "input_signal_ids",
        "rationale",
    }
    missing = sorted(required - set(decision))
    if missing:
        raise ValueError(f"ResearchPlanningDecision is missing required fields: {missing}")

    result = deepcopy(dict(decision))

    # Semantic isolation is checked before optional-field type validation.
    # This guarantees that a forbidden scientific meaning cannot be hidden
    # inside an otherwise malformed generic field such as created_at.
    forbidden_terms = {
        "confidence",
        "evidence_strength",
        "evidence_gap",
        "epistemic_status",
        "truth_status",
        "truth_probability",
        "claim_rank",
        "claim_ranking",
        "convergence",
        "convergence_score",
        "scientific_priority",
    }

    def find_forbidden(value: Any) -> str | None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if str(key).strip().casefold() in forbidden_terms:
                    return str(key)
                found = find_forbidden(child)
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = find_forbidden(child)
                if found:
                    return found
        return None

    forbidden = find_forbidden(result)
    if forbidden:
        raise ValueError(f"forbidden scientific semantic field: {forbidden!r}")

    _require_non_empty_string(
        result["research_planning_decision_id"],
        "research_planning_decision_id",
    )
    decision_type = _require_non_empty_string(result["decision_type"], "decision_type")
    if decision_type not in ALLOWED_DECISION_TYPES:
        raise ValueError(f"unsupported decision_type: {decision_type!r}")

    signal_ids = _string_list(result["input_signal_ids"], "input_signal_ids")
    if not signal_ids:
        raise ValueError("input_signal_ids must not be empty")
    _require_non_empty_string(result["rationale"], "rationale")

    if "priority" in result:
        priority = result["priority"]
        if isinstance(priority, bool) or not isinstance(priority, (int, float)):
            raise ValueError("priority must be numeric")
        if not 0.0 <= float(priority) <= 1.0:
            raise ValueError("priority must be between 0.0 and 1.0")

    if "target" in result:
        target = result["target"]
        if not isinstance(target, Mapping):
            raise ValueError("target must be a mapping")
        unknown_target = sorted(set(target) - {"query_scope", "provider"})
        if unknown_target:
            raise ValueError(f"unknown decision target fields: {unknown_target}")
        for field in target:
            _require_non_empty_string(target[field], f"target.{field}")

    if "created_at" in result:
        _require_non_empty_string(result["created_at"], "created_at")
    if "planner_version" in result:
        _require_non_empty_string(result["planner_version"], "planner_version")
    if "acquisition_request_reference" in result:
        _require_non_empty_string(
            result["acquisition_request_reference"],
            "acquisition_request_reference",
        )

    return result


__all__ = [
    "ALLOWED_DECISION_TYPES",
    "PLANNER_VERSION",
    "PLANNING_DECISION_SCHEMA_VERSION",
    "evaluate_research_planning_signal",
    "evaluate_research_planning_signals",
    "validate_research_planning_decision",
]
