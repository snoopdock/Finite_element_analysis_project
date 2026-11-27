"""C-condition preflight only: validates B provenance and manual authorization.

This module never imports a provider factory, reads credentials, creates a
provider instance, or performs a network request. A ready result means only
that a separate manually dispatched C executor may be considered.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from tools.ae32d_deterministic_audit import REPORT_SCHEMA
from tools.ae32d_trial_contracts import canonical_json_bytes

ROOT = Path(__file__).resolve().parents[1]
AUTH_SCHEMA = ROOT / "evaluation" / "ae32d" / "c-authorization.schema.json"
PREFLIGHT_SCHEMA = ROOT / "evaluation" / "ae32d" / "c-preflight.schema.json"
PROMPT_SOURCE = ROOT / "audit_engine" / "semantic_audit" / "ae32c" / "investigator.py"
RESPONSE_PROTOCOL_SOURCE = ROOT / "audit_engine" / "semantic_audit" / "ae32c" / "response_protocol.py"
TOOL_SOURCE = ROOT / "audit_engine" / "semantic_audit" / "ae32b" / "evidence_tools.py"
TOOL_POLICY_SOURCE = ROOT / "audit_engine" / "semantic_audit" / "ae32c" / "tool_policy.py"
COST_ESTIMATOR_SOURCE = ROOT / "audit_engine" / "semantic_audit" / "ae32c" / "live_evaluation.py"
CONFIRMATION_PHRASE = "I_AUTHORIZE_ONE_AE32D_C_PROVIDER_RUN"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source_digests() -> dict[str, str]:
    return {
        "prompt_source_sha256": _sha256(PROMPT_SOURCE.read_bytes() + RESPONSE_PROTOCOL_SOURCE.read_bytes()),
        "tool_catalog_sha256": _sha256(TOOL_SOURCE.read_bytes() + TOOL_POLICY_SOURCE.read_bytes()),
        "cost_estimator_sha256": _sha256(COST_ESTIMATOR_SOURCE.read_bytes()),
    }


def _b_snapshot_issues(report: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    baseline = report.get("baseline_report", {})
    if report.get("condition") != "B_graph":
        issues.append("condition_is_not_B_graph")
    if baseline.get("condition") != "A_deterministic":
        issues.append("embedded_baseline_is_not_A")
    for key in ("case_id", "source_commit_sha", "task_contract_digest", "source_manifest_digest"):
        if report.get(key) != baseline.get(key):
            issues.append("A_B_identity_mismatch:" + key)
    if report.get("baseline_config_digest") != baseline.get("config_digest"):
        issues.append("baseline_config_digest_mismatch")
    for key in ("findings", "counterevidence", "unresolved_questions", "decision"):
        if report.get(key) != baseline.get(key):
            issues.append("A_evidence_or_decision_not_preserved:" + key)

    coverage = report.get("coverage", {})
    if coverage.get("declared_scope_complete") is not True:
        issues.append("declared_scope_incomplete")
    if coverage.get("truncated") is True:
        issues.append("B_coverage_truncated")
    if coverage.get("missing_paths"):
        issues.append("B_missing_scope_paths")
    if coverage.get("unreadable_paths"):
        issues.append("B_unreadable_scope_paths")

    graph = report.get("graph_snapshot", {})
    if graph.get("status") != "complete":
        issues.append("graph_snapshot_incomplete")
    if graph.get("source_revision") != report.get("source_commit_sha"):
        issues.append("graph_source_revision_mismatch")
    if graph.get("backend_pipeline_wired") is not True:
        issues.append("graph_backend_not_wired")
    if graph.get("graph_backend") != "networkx":
        issues.append("unexpected_graph_backend")

    retrieval = report.get("graph_retrieval", [])
    if not retrieval:
        issues.append("graph_retrieval_missing")
    if any(item.get("status") != "ok" for item in retrieval):
        issues.append("graph_retrieval_error")
    if any(item.get("truncated") is True or item.get("coverage_status") == "partial" for item in retrieval):
        issues.append("graph_retrieval_incomplete")
    if not any(
        item.get("tool") == "graph_neighbors"
        and item.get("status") == "ok"
        and item.get("payload", {}).get("discovered_nodes")
        for item in retrieval
    ):
        issues.append("nonempty_graph_neighbor_evidence_missing")
    if not any(item.get("tool") == "repository_summary" and item.get("status") == "ok" for item in retrieval):
        issues.append("graph_repository_summary_missing")
    return sorted(set(issues))


def build_c_preflight(
    b_report: dict[str, Any], authorization: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Validate B package and optional manual authorization without provider access."""
    report_schema = json.loads(REPORT_SCHEMA.read_text(encoding="utf-8"))
    auth_schema = json.loads(AUTH_SCHEMA.read_text(encoding="utf-8"))
    output_schema = json.loads(PREFLIGHT_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(report_schema).validate(b_report)
    Draft202012Validator(auth_schema).check_schema(auth_schema)
    Draft202012Validator(output_schema).check_schema(output_schema)

    baseline = b_report["baseline_report"]
    Draft202012Validator(report_schema).validate(baseline)
    b_digest = _sha256(canonical_json_bytes(b_report))
    graph_fingerprint = b_report["graph_snapshot"]["graph_fingerprint"]
    source_digests = _source_digests()
    b_issues = _b_snapshot_issues(b_report)

    authorization_status = "absent" if authorization is None else "invalid"
    authorization_issues: list[str] = []
    if authorization is not None:
        try:
            Draft202012Validator(auth_schema).validate(authorization)
        except Exception:
            authorization_issues.append("authorization_schema_invalid")
        else:
            expected_bindings = {
                "case_id": b_report["case_id"],
                "source_commit_sha": b_report["source_commit_sha"],
                "task_contract_digest": b_report["task_contract_digest"],
                "b_report_sha256": b_digest,
                "graph_fingerprint": graph_fingerprint,
                **source_digests,
            }
            for key, expected in expected_bindings.items():
                if authorization.get(key) != expected:
                    authorization_issues.append("authorization_binding_mismatch:" + key)
            if authorization.get("confirmation_phrase") != CONFIRMATION_PHRASE:
                authorization_issues.append("manual_confirmation_phrase_mismatch")
            if not authorization_issues:
                authorization_status = "valid"

    if b_issues:
        status = "blocked_incomplete_B_snapshot"
        blocking_reasons = b_issues + authorization_issues
    elif authorization is None:
        status = "blocked_manual_authorization_required"
        blocking_reasons = ["manual_authorization_required"]
    elif authorization_status != "valid":
        status = "blocked_invalid_authorization"
        blocking_reasons = authorization_issues or ["authorization_invalid"]
    else:
        status = "ready_for_manual_dispatch"
        blocking_reasons = []

    authorized_plan = authorization if authorization_status == "valid" else {}
    request_plan = {
        "provider_name": authorized_plan.get("provider_name"),
        "model_name": authorized_plan.get("model_name"),
        "authorization_id": authorized_plan.get("authorization_id"),
        "budget": {
            "max_model_rounds": authorized_plan.get("max_model_rounds"),
            "max_tool_calls": authorized_plan.get("max_tool_calls"),
            "max_tokens_per_call": authorized_plan.get("max_tokens_per_call"),
            "finalization_max_tokens_per_call": authorized_plan.get("finalization_max_tokens_per_call"),
            "max_total_tokens": authorized_plan.get("max_total_tokens"),
            "max_elapsed_seconds": authorized_plan.get("max_elapsed_seconds"),
            "max_cost_usd": authorized_plan.get("max_cost_usd"),
        },
    }
    output = {
        "schema_version": "ae32d/c-preflight/v1",
        "status": status,
        "authorization_status": authorization_status,
        "case_id": b_report["case_id"],
        "source_commit_sha": b_report["source_commit_sha"],
        "task_contract_digest": b_report["task_contract_digest"],
        "b_report_sha256": b_digest,
        "graph_fingerprint": graph_fingerprint,
        "graph_backend": b_report["graph_snapshot"]["graph_backend"],
        **source_digests,
        "provider_dispatch_permitted": False,
        "provider_calls_attempted": 0,
        "credentials_accessed": False,
        "manual_dispatch_required": True,
        "blocking_reasons": blocking_reasons,
        "request_plan": request_plan,
    }
    Draft202012Validator(output_schema).validate(output)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate AE-32D C preflight; never calls a provider")
    parser.add_argument("--b-report", required=True, help="Path to a retained B_graph report JSON file")
    parser.add_argument("--authorization", default=None, help="Optional explicit C authorization JSON envelope")
    parser.add_argument("--output", default=None, help="Optional output JSON path")
    args = parser.parse_args(argv)
    b_report = json.loads(Path(args.b_report).read_text(encoding="utf-8"))
    authorization = (
        json.loads(Path(args.authorization).read_text(encoding="utf-8"))
        if args.authorization else None
    )
    result = build_c_preflight(b_report, authorization)
    rendered = json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["status"] == "ready_for_manual_dispatch" else 2


if __name__ == "__main__":
    raise SystemExit(main())
