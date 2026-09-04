#!/usr/bin/env python3
"""Form explicit AcquisitionRequest objects from research-planning decisions."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from analysis.acquisition_adapter import validate_acquisition_request
from analysis.research_planning_decision import validate_research_planning_decision


FORMULATION_SCHEMA_VERSION = 1

_ALLOWED_CONSTRAINT_FIELDS = {
    "provider_preferences",
    "provider_access_constraints",
    "execution_limits",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_request_id() -> str:
    return f"acquisition-request-{uuid4().hex}"


def _validate_operational_constraints(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError("operational_constraints must be a mapping")

    unknown = sorted(set(value) - _ALLOWED_CONSTRAINT_FIELDS)
    if unknown:
        raise ValueError(f"unknown operational acquisition constraints: {unknown}")

    return deepcopy(dict(value))


def formulate_acquisition_request(
    decision: Mapping[str, Any],
    *,
    operational_constraints: Mapping[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Create one explicit AcquisitionRequest without executing acquisition."""
    validated_decision = validate_research_planning_decision(decision)

    if validated_decision["decision_type"] != "formulate_acquisition_request":
        raise ValueError(
            "ResearchPlanningDecision must have decision_type="
            "formulate_acquisition_request"
        )

    target = validated_decision.get("target")
    if not isinstance(target, Mapping):
        raise ValueError(
            "ResearchPlanningDecision.target.query_scope is required for request formulation"
        )

    query_scope = target.get("query_scope")
    if not isinstance(query_scope, str) or not query_scope.strip():
        raise ValueError(
            "ResearchPlanningDecision.target.query_scope is required for request formulation"
        )

    # target.provider is deliberately not mapped into AcquisitionRequest
    # provider_preferences or provider_access_constraints. Its planning meaning
    # is not provider-selection authority.
    constraints = _validate_operational_constraints(operational_constraints)

    priority = validated_decision.get("priority", 0.0)
    if priority is None:
        priority = 0.0

    request = {
        "acquisition_request_id": _new_request_id(),
        "schema_version": FORMULATION_SCHEMA_VERSION,
        "created_at": created_at or _now(),
        "origin": {
            "research_planning_decision_id": validated_decision[
                "research_planning_decision_id"
            ]
        },
        "target": {
            "query_scope": query_scope.strip(),
        },
        "constraints": constraints,
        "priority": float(priority),
    }

    return validate_acquisition_request(request)


__all__ = [
    "FORMULATION_SCHEMA_VERSION",
    "formulate_acquisition_request",
]
