"""AE-45 C3 execution contract: provider-free authorization and budget gate.

This module validates the prepared C request against a fresh C0 preflight.
It deliberately does not import a provider factory, read credentials, perform
network I/O, or start the AE-32C investigator. A later executor may construct
a provider only after this contract returns the authorized status.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator

from tools.ae32d_c_preflight import build_c_preflight
from tools.ae32d_trial_contracts import canonical_json_bytes
from tools.ae32d_deterministic_audit import ROOT

REQUEST_PACKAGE_SCHEMA = ROOT / "evaluation" / "ae32d" / "c-request-package.schema.json"
PROFILE = ("cloudflare", "@cf/qwen/qwen3.8-27b")
HARD_LIMITS = {
    "max_model_rounds": 11,
    "max_tool_calls": 12,
    "max_total_tokens": 30_720,
    "max_elapsed_seconds": 900,
    "max_cost_usd": 0.50,
}


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or len(value) > 400:
        return False
    if "\\" in value or value.startswith("/"):
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and all(part not in {"", ".", ".."} for part in value.split("/"))


def _validated_budget(budget: dict[str, Any]) -> dict[str, int | float]:
    """Map the exact authorized budget; never widen any value."""
    if not isinstance(budget, dict):
        raise ValueError("C3_budget_missing")
    required = (
        "max_model_rounds",
        "max_tool_calls",
        "max_tokens_per_call",
        "finalization_max_tokens_per_call",
        "max_total_tokens",
        "max_elapsed_seconds",
        "max_cost_usd",
    )
    if set(budget) != set(required):
        raise ValueError("C3_budget_fields_mismatch")
    for key in required[:-1]:
        value = budget[key]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("C3_budget_invalid:" + key)
    cost = budget["max_cost_usd"]
    if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost <= 0:
        raise ValueError("C3_budget_invalid:max_cost_usd")
    for key, ceiling in HARD_LIMITS.items():
        if budget[key] > ceiling:
            raise ValueError("C3_budget_exceeds_hard_limit:" + key)
    if budget["max_tokens_per_call"] > 2_048:
        raise ValueError("C3_budget_exceeds_hard_limit:max_tokens_per_call")
    if budget["finalization_max_tokens_per_call"] > 6_144:
        raise ValueError("C3_budget_exceeds_hard_limit:finalization_max_tokens_per_call")
    return {
        "max_rounds": budget["max_model_rounds"],
        "max_tool_calls": budget["max_tool_calls"],
        "max_tokens_per_call": budget["max_tokens_per_call"],
        "finalization_max_tokens_per_call": budget["finalization_max_tokens_per_call"],
        "max_total_tokens": budget["max_total_tokens"],
        "max_elapsed_seconds": budget["max_elapsed_seconds"],
        "max_cost_usd": float(cost),
        "temperature": 0.0,
    }


def build_c3_execution_contract(
    b_report: dict[str, Any],
    request_package: dict[str, Any],
    authorization: dict[str, Any],
    *,
    manual_dispatch_confirmed: bool = False,
) -> dict[str, Any]:
    """Validate C0/C1/C2 bindings and produce a provider-free C3 contract.

    The confirmation flag is a separate operator/workflow control. Even when
    true, this function only authorizes provider construction; it never
    constructs a provider or starts an investigation.
    """
    schema = json.loads(REQUEST_PACKAGE_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(request_package)

    if type(manual_dispatch_confirmed) is not bool:
        raise ValueError("C3_manual_dispatch_confirmation_must_be_boolean")
    if request_package["status"] != "prepared_manual_only":
        raise ValueError("C3_request_not_prepared")
    request = request_package.get("request")
    if not isinstance(request, dict):
        raise ValueError("C3_request_missing")
    if request_package["manual_dispatch_confirmed"] is not False:
        raise ValueError("C3_prepared_package_must_not_claim_dispatch_confirmation")
    if request_package["provider_dispatch_permitted"] is not False:
        raise ValueError("C3_prepared_package_must_not_permit_dispatch")
    if request_package["provider_calls_attempted"] != 0 or request_package["credentials_accessed"] is not False:
        raise ValueError("C3_prepared_package_has_provider_side_effect_claims")

    request_digest = _sha256(canonical_json_bytes(request))
    if request_package.get("request_sha256") != request_digest:
        raise ValueError("C3_request_digest_mismatch")

    fresh_preflight = build_c_preflight(b_report, authorization)
    if request_package.get("preflight") != fresh_preflight:
        raise ValueError("C3_preflight_binding_mismatch")
    if fresh_preflight.get("status") != "ready_for_manual_dispatch":
        return {
            "schema_version": "ae32d/c3-execution-contract/v1",
            "status": "blocked",
            "blocking_reasons": list(fresh_preflight.get("blocking_reasons", [])),
            "provider_dispatch_permitted": False,
            "provider_calls_attempted": 0,
            "credentials_accessed": False,
            "investigator_limits": None,
        }

    expected_bindings = {
        "case_id": fresh_preflight["case_id"],
        "source_commit_sha": fresh_preflight["source_commit_sha"],
        "task_contract_digest": fresh_preflight["task_contract_digest"],
        "b_report_sha256": fresh_preflight["b_report_sha256"],
        "graph_fingerprint": fresh_preflight["graph_fingerprint"],
        "prompt_source_sha256": fresh_preflight["prompt_source_sha256"],
        "tool_catalog_sha256": fresh_preflight["tool_catalog_sha256"],
        "cost_estimator_sha256": fresh_preflight["cost_estimator_sha256"],
    }
    for key, expected in expected_bindings.items():
        if request.get(key) != expected:
            raise ValueError("C3_request_binding_mismatch:" + key)

    if (request.get("provider_name"), request.get("model_name")) != PROFILE:
        raise ValueError("C3_provider_model_profile_unsupported")
    if request.get("authorization_sha256") != _sha256(canonical_json_bytes(authorization)):
        raise ValueError("C3_authorization_digest_mismatch")

    plan = fresh_preflight.get("request_plan", {})
    if request.get("provider_name") != plan.get("provider_name"):
        raise ValueError("C3_provider_plan_mismatch")
    if request.get("model_name") != plan.get("model_name"):
        raise ValueError("C3_model_plan_mismatch")
    limits = _validated_budget(request.get("budget", {}))
    if request.get("budget") != plan.get("budget"):
        raise ValueError("C3_budget_plan_mismatch")

    requirements = request.get("investigation_requirements")
    if not isinstance(requirements, dict):
        raise ValueError("C3_investigation_requirements_missing")
    source_paths = requirements.get("required_source_paths")
    if (not isinstance(source_paths, list) or not source_paths
            or len(source_paths) > 12
            or len(source_paths) != len(set(source_paths))
            or not all(_safe_relative_path(path) for path in source_paths)):
        raise ValueError("C3_required_source_paths_invalid")
    graph_target = requirements.get("required_graph_target")
    relation_types = requirements.get("required_graph_relation_types")
    if not isinstance(graph_target, str) or not graph_target.strip() or len(graph_target) > 400:
        raise ValueError("C3_required_graph_target_invalid")
    if (not isinstance(relation_types, list) or not relation_types
            or len(relation_types) > 12
            or len(relation_types) != len(set(relation_types))
            or not all(isinstance(item, str) and item.strip() for item in relation_types)):
        raise ValueError("C3_graph_relation_types_invalid")
    if requirements.get("required_graph_direction") not in {"incoming", "outgoing", "both"}:
        raise ValueError("C3_graph_direction_invalid")
    if requirements.get("require_graph_interaction") is not True:
        raise ValueError("C3_graph_interaction_must_be_required")
    if requirements.get("require_complete_investigation_context") is not True:
        raise ValueError("C3_complete_context_must_be_required")
    if requirements.get("prefetch_required_graph_query") is not True:
        raise ValueError("C3_graph_query_prefetch_must_be_required")

    confirmed = manual_dispatch_confirmed and authorization.get("approved") is True
    return {
        "schema_version": "ae32d/c3-execution-contract/v1",
        "status": "authorized_for_provider_construction" if confirmed else "ready_for_manual_confirmation",
        "case_id": request["case_id"],
        "source_commit_sha": request["source_commit_sha"],
        "task_contract_digest": request["task_contract_digest"],
        "b_report_sha256": request["b_report_sha256"],
        "graph_fingerprint": request["graph_fingerprint"],
        "request_sha256": request_digest,
        "authorization_sha256": request["authorization_sha256"],
        "provider_name": request["provider_name"],
        "model_name": request["model_name"],
        "investigator_limits": limits,
        "investigation_requirements": requirements,
        "provider_dispatch_permitted": False,
        "provider_calls_attempted": 0,
        "credentials_accessed": False,
        "manual_dispatch_confirmed": confirmed,
        "note": "Contract validation only; no provider was constructed and no request was sent.",
    }
