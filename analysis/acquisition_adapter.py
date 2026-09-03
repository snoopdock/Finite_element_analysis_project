#!/usr/bin/env python3
"""Translate and execute explicit AcquisitionRequest objects.

R8.7.4 intentionally implements only the acquisition boundary. The
AcquisitionRequest remains the authoritative semantic model; the current
retrieval runtime continues to accept List[str]. Translation loss is recorded
as execution provenance rather than being pushed into EvidenceRecord.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import uuid
from typing import Any, Callable, Mapping

from research.evidence import get_last_retrieval_report, retrieve_evidence_parallel


ACQUISITION_ADAPTER_SCHEMA_VERSION = 1
TRANSLATION_POLICY_VERSION = "r8.7.4-v1"

_ALLOWED_REQUEST_FIELDS = {
    "acquisition_request_id",
    "schema_version",
    "created_at",
    "origin",
    "target",
    "constraints",
    "priority",
    "requester",
    "request_version",
    "notes",
}
_REQUIRED_REQUEST_FIELDS = {
    "acquisition_request_id",
    "schema_version",
    "created_at",
    "origin",
    "target",
    "constraints",
    "priority",
}
_ALLOWED_CONSTRAINT_FIELDS = {
    "provider_preferences",
    "provider_access_constraints",
    "execution_limits",
}
_ALLOWED_RECEIPT_STATUSES = {
    "success",
    "failure",
    "partial_failure",
    "empty_result",
    "rate_limited",
}

_FORBIDDEN_SCIENTIFIC_FIELDS = {
    "confidence",
    "confidence_score",
    "evidence_gap",
    "evidence_strength",
    "evidence_quality",
    "epistemic_status",
    "truth_status",
    "truth_probability",
    "ranking",
    "ranking_score",
    "claim_rank",
    "claim_ranking",
    "convergence",
    "convergence_score",
    "scientific_priority",
    "scientific_importance",
    "scientific_relevance",
    "claim_id",
    "proposition_id",
    "evidence_relation",
}


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field} must be a mapping")
    return value


def _reject_scientific_fields(value: Any, path: str = "request") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_SCIENTIFIC_FIELDS:
                raise ValueError(
                    f"forbidden scientific semantic field in AcquisitionRequest: {path}.{key}"
                )
            _reject_scientific_fields(nested, f"{path}.{key}")
    elif isinstance(value, (list, tuple, set)):
        for index, nested in enumerate(value):
            _reject_scientific_fields(nested, f"{path}[{index}]")


def _validate_string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{field} must be a list or tuple")
    result: list[str] = []
    for item in value:
        result.append(_require_string(item, field))
    if len(set(result)) != len(result):
        raise ValueError(f"{field} must not contain duplicates")
    return result


def _validate_constraints(constraints: Mapping[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(constraints) - _ALLOWED_CONSTRAINT_FIELDS)
    if unknown:
        raise ValueError(f"unknown AcquisitionRequest constraints: {unknown}")

    normalized: dict[str, Any] = {}

    if "provider_preferences" in constraints:
        normalized["provider_preferences"] = _validate_string_list(
            constraints["provider_preferences"],
            "constraints.provider_preferences",
        )

    if "provider_access_constraints" in constraints:
        access = _require_mapping(
            constraints["provider_access_constraints"],
            "constraints.provider_access_constraints",
        )
        normalized["provider_access_constraints"] = deepcopy(dict(access))

    if "execution_limits" in constraints:
        limits = _require_mapping(
            constraints["execution_limits"],
            "constraints.execution_limits",
        )
        normalized["execution_limits"] = deepcopy(dict(limits))

    return normalized


def validate_acquisition_request(
    request: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate an AcquisitionRequest and return a defensive normalized copy."""
    if not isinstance(request, Mapping):
        raise TypeError("AcquisitionRequest must be a mapping")

    unknown = sorted(set(request) - _ALLOWED_REQUEST_FIELDS)
    if unknown:
        raise ValueError(f"unknown AcquisitionRequest fields: {unknown}")

    missing = sorted(_REQUIRED_REQUEST_FIELDS - set(request))
    if missing:
        raise ValueError(f"AcquisitionRequest is missing required fields: {missing}")

    _reject_scientific_fields(request)

    result = deepcopy(dict(request))
    _require_string(result["acquisition_request_id"], "acquisition_request_id")

    schema_version = result["schema_version"]
    if isinstance(schema_version, bool) or not isinstance(schema_version, int) or schema_version < 1:
        raise ValueError("schema_version must be an integer >= 1")

    _require_string(result["created_at"], "created_at")

    origin = _require_mapping(result["origin"], "origin")
    if set(origin) != {"research_planning_decision_id"}:
        unknown_origin = sorted(set(origin) - {"research_planning_decision_id"})
        missing_origin = "research_planning_decision_id" not in origin
        if missing_origin:
            raise ValueError("origin.research_planning_decision_id is required")
        raise ValueError(f"unknown AcquisitionRequest origin fields: {unknown_origin}")
    _require_string(
        origin["research_planning_decision_id"],
        "origin.research_planning_decision_id",
    )

    target = _require_mapping(result["target"], "target")
    if set(target) != {"query_scope"}:
        unknown_target = sorted(set(target) - {"query_scope"})
        raise ValueError(f"unknown AcquisitionRequest target fields: {unknown_target}")
    _require_string(target["query_scope"], "target.query_scope")

    constraints = _require_mapping(result["constraints"], "constraints")
    result["constraints"] = _validate_constraints(constraints)

    priority = result["priority"]
    if isinstance(priority, bool) or not isinstance(priority, (int, float)):
        raise ValueError("priority must be numeric")
    if not 0.0 <= float(priority) <= 1.0:
        raise ValueError("priority must be between 0.0 and 1.0")
    result["priority"] = float(priority)

    return result


def _query_inputs(query_scope: str) -> list[str]:
    normalized = _require_string(query_scope, "target.query_scope")
    return [normalized]


def project_acquisition_request(
    request: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the precise internal execution projection without performing retrieval."""
    normalized = validate_acquisition_request(request)
    constraints = normalized["constraints"]

    query_inputs = _query_inputs(normalized["target"]["query_scope"])
    translation_results: dict[str, dict[str, Any]] = {
        "target.query_scope": {
            "class": "translated",
            "semantic_status": "represented_as_legacy_query_input",
        },
        "priority": {
            "class": "preserved",
            "semantic_status": "retained_as_process_metadata",
            "value": normalized["priority"],
        },
    }
    translation_losses: list[dict[str, Any]] = []
    execution_constraints_applied: list[str] = []

    if "provider_preferences" in constraints:
        translation_results["constraints.provider_preferences"] = {
            "class": "unrepresentable",
            "semantic_status": "not_enforced_by_current_retrieval_interface",
        }
        translation_losses.append(
            {
                "field": "constraints.provider_preferences",
                "class": "unrepresentable",
                "reason": "The current retrieval interface does not expose provider-selection semantics.",
            }
        )

    if "provider_access_constraints" in constraints:
        translation_results["constraints.provider_access_constraints"] = {
            "class": "unrepresentable",
            "semantic_status": "not_enforced_by_current_retrieval_interface",
        }
        translation_losses.append(
            {
                "field": "constraints.provider_access_constraints",
                "class": "unrepresentable",
                "reason": "The current retrieval interface does not expose provider-access restriction semantics.",
            }
        )

    if "execution_limits" in constraints:
        translation_results["constraints.execution_limits"] = {
            "class": "unrepresentable",
            "semantic_status": "not_enforced_by_current_retrieval_interface",
        }
        translation_losses.append(
            {
                "field": "constraints.execution_limits",
                "class": "unrepresentable",
                "reason": "No exact semantic equivalent is exposed by the current retrieval boundary.",
            }
        )

    return {
        "acquisition_request_id": normalized["acquisition_request_id"],
        "translation_policy_version": TRANSLATION_POLICY_VERSION,
        "query_inputs": query_inputs,
        "translation_results": translation_results,
        "translation_losses": translation_losses,
        "execution_constraints_applied": execution_constraints_applied,
        "priority": normalized["priority"],
        "request": normalized,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_execution_id() -> str:
    return f"acquisition-execution-{uuid.uuid4().hex}"


def _execution_status_from_report(
    report: Mapping[str, Any] | None,
    results: Any,
) -> str:
    if isinstance(report, Mapping):
        status = str(report.get("status", "")).strip()
        if status in _ALLOWED_RECEIPT_STATUSES:
            if status == "failure":
                providers = report.get("providers")
                if isinstance(providers, Mapping) and providers:
                    provider_statuses = [
                        str(value.get("status", "")).strip()
                        for value in providers.values()
                        if isinstance(value, Mapping)
                    ]
                    if provider_statuses and all(item == "rate_limited" for item in provider_statuses):
                        return "rate_limited"
            return status

    if isinstance(results, list):
        return "success" if results else "empty_result"
    return "failure"


def _receipt(
    *,
    execution_id: str,
    acquisition_request_id: str,
    started_at: str,
    completed_at: str,
    execution_status: str,
    projection: Mapping[str, Any],
    provider_execution_summary: Any = None,
    error_summary: str | None = None,
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "execution_id": execution_id,
        "acquisition_request_id": acquisition_request_id,
        "started_at": started_at,
        "completed_at": completed_at,
        "execution_status": execution_status,
        "translation_policy_version": projection["translation_policy_version"],
        "translation_results": deepcopy(projection["translation_results"]),
        "translation_losses": deepcopy(projection["translation_losses"]),
        "execution_constraints_applied": deepcopy(projection["execution_constraints_applied"]),
        "generated_query_inputs": deepcopy(projection["query_inputs"]),
        "provider_execution_summary": deepcopy(provider_execution_summary),
    }
    if error_summary:
        receipt["error_summary"] = str(error_summary)
    return receipt


def execute_acquisition_request(
    request: Mapping[str, Any],
    *,
    max_items: int = 4,
    max_workers: int = 3,
    max_per_provider: int = 2,
    max_per_source_type: int = 3,
    retrieval_executor: Callable[..., list[dict[str, Any]]] | None = None,
    retrieval_report_getter: Callable[[], Mapping[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Execute one explicit AcquisitionRequest and return results plus its receipt."""
    projection = project_acquisition_request(request)
    execution_id = _new_execution_id()
    started_at = _now()

    queries = projection["query_inputs"]
    if not queries:
        completed_at = _now()
        receipt = _receipt(
            execution_id=execution_id,
            acquisition_request_id=projection["acquisition_request_id"],
            started_at=started_at,
            completed_at=completed_at,
            execution_status="failure",
            projection=projection,
            error_summary="AcquisitionRequest translated to no executable query inputs.",
        )
        return [], receipt

    executor = retrieval_executor or retrieve_evidence_parallel
    report_getter = retrieval_report_getter or get_last_retrieval_report

    try:
        results = executor(
            queries,
            max_items=max_items,
            max_workers=max_workers,
            max_per_provider=max_per_provider,
            max_per_source_type=max_per_source_type,
        )
        if not isinstance(results, list):
            raise TypeError("retrieval executor returned a non-list result")
        report = report_getter()
        status = _execution_status_from_report(report, results)
        completed_at = _now()
        receipt = _receipt(
            execution_id=execution_id,
            acquisition_request_id=projection["acquisition_request_id"],
            started_at=started_at,
            completed_at=completed_at,
            execution_status=status,
            projection=projection,
            provider_execution_summary=report.get("providers") if isinstance(report, Mapping) else report,
        )
        return results, receipt
    except Exception as exc:
        completed_at = _now()
        receipt = _receipt(
            execution_id=execution_id,
            acquisition_request_id=projection["acquisition_request_id"],
            started_at=started_at,
            completed_at=completed_at,
            execution_status="failure",
            projection=projection,
            error_summary=str(exc),
        )
        return [], receipt


__all__ = [
    "ACQUISITION_ADAPTER_SCHEMA_VERSION",
    "TRANSLATION_POLICY_VERSION",
    "execute_acquisition_request",
    "project_acquisition_request",
    "validate_acquisition_request",
]
