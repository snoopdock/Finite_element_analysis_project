"""C1 request packaging: prepares an exact B-bound investigator request, never dispatches it."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from jsonschema import Draft202012Validator

from tools.ae32d_c_preflight import (
    build_c_preflight,
)
from tools.ae32d_deterministic_audit import ROOT, TASK_SCHEMA, _scope_relative_path
from tools.ae32d_trial_contracts import canonical_json_bytes


REQUEST_SCHEMA = ROOT / "evaluation" / "ae32d" / "c-request-package.schema.json"
MAX_CONTEXT_ITEMS = 24


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _bounded_payload(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "discovered_nodes", "observations", "evidence", "symbols", "path", "paths",
        "tests", "source_paths", "caller_relationships", "dependency_relationships",
        "entrypoints", "context_paths", "coverage_status", "truncated",
        "graph_node_count", "graph_edge_count",
    )
    result: dict[str, Any] = {}
    for key in allowed:
        value = payload.get(key)
        if isinstance(value, list):
            result[key] = value[:MAX_CONTEXT_ITEMS]
        elif value is not None and isinstance(value, (str, int, float, bool, dict)):
            result[key] = value
    return result


def build_c_request_package(
    task_projection: dict[str, Any],
    b_report: dict[str, Any],
    authorization: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare a bounded C request package; manual dispatch remains disabled."""
    task_schema = json.loads(TASK_SCHEMA.read_text(encoding="utf-8"))
    output_schema = json.loads(REQUEST_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(task_schema).validate(task_projection)
    Draft202012Validator(output_schema).check_schema(output_schema)
    if task_projection["condition"] != "C_graph_llm":
        raise ValueError("C_request_requires_C_graph_llm_projection")

    preflight = build_c_preflight(b_report, authorization)
    if task_projection["case_id"] != b_report["case_id"]:
        raise ValueError("C_projection_case_mismatch")
    if task_projection["source"]["source_commit_sha"] != b_report["source_commit_sha"]:
        raise ValueError("C_projection_source_mismatch")
    if task_projection["task_contract_digest"] != b_report["task_contract_digest"]:
        raise ValueError("C_projection_task_digest_mismatch")

    request = None
    request_digest = None
    status = "blocked"
    if preflight["status"] == "ready_for_manual_dispatch":
        fixture_path = task_projection["source"]["fixture_path"]
        required_source_paths = sorted({
            relative for item in task_projection["task"]["declared_scope"]
            if (relative := _scope_relative_path(item, fixture_path)) is not None
        })
        python_paths = [path for path in required_source_paths if path.endswith(".py")]
        if not python_paths:
            raise ValueError("C_request_requires_at_least_one_python_source_path")

        retrieval_context = []
        required_context_target = None
        for item in b_report["graph_retrieval"]:
            payload = item["payload"]
            if item["tool"] == "trace_execution_context":
                target = item["arguments"].get("target")
                if isinstance(target, str) and target in python_paths:
                    required_context_target = target
            retrieval_context.append({
                "tool": item["tool"],
                "arguments": item["arguments"],
                "status": item["status"],
                "coverage_status": item["coverage_status"],
                "truncated": item["truncated"],
                "response_digest": item["response_digest"],
                "provenance": item["provenance"],
                "payload": _bounded_payload(payload),
            })

        baseline = b_report["baseline_report"]
        context = {
            "task_title": task_projection["task"]["title"],
            "task_problem_statement": task_projection["task"]["problem_statement"],
            "declared_scope": task_projection["task"]["declared_scope"],
            "a_baseline": {
                "decision": baseline["decision"],
                "findings": baseline["findings"][:MAX_CONTEXT_ITEMS],
                "counterevidence": baseline["counterevidence"][:MAX_CONTEXT_ITEMS],
                "unresolved_questions": baseline["unresolved_questions"][:MAX_CONTEXT_ITEMS],
                "limitations": baseline["limitations"][:MAX_CONTEXT_ITEMS],
                "config_digest": baseline["config_digest"],
            },
            "b_graph": {
                "graph_snapshot": b_report["graph_snapshot"],
                "retrieval": retrieval_context,
            },
            "interpretation_rule": (
                "A and B are machine-generated investigative context, not ground truth. "
                "Independently inspect the pinned source and graph evidence. Do not treat "
                "their decisions or findings as authoritative labels. Distinguish observations, "
                "inferences, counterevidence and unresolved questions; abstain when evidence is insufficient."
            ),
        }
        def _brief_items(items: list[Any], *, maximum: int = 2, limit: int = 220) -> list[str]:
            """Create a small prompt-only synopsis; the full records remain in context."""
            result = []
            for item in items[:maximum]:
                if isinstance(item, dict):
                    candidate = next((
                        item[key] for key in (
                            "statement", "summary", "finding", "question", "description", "limitation"
                        ) if isinstance(item.get(key), str) and item[key].strip()
                    ), None)
                else:
                    candidate = item if isinstance(item, str) else None
                if candidate is None:
                    candidate = json.dumps(item, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
                result.append(str(candidate)[:limit])
            return result

        graph_snapshot = context["b_graph"]["graph_snapshot"]
        graph_retrieval_briefs = []
        for item in context["b_graph"]["retrieval"]:
            payload = item["payload"] if isinstance(item.get("payload"), dict) else {}
            graph_retrieval_briefs.append({
                "tool": item["tool"],
                "status": item["status"],
                "coverage_status": item["coverage_status"],
                "response_digest": item["response_digest"],
                "relation_types": payload.get("observed_relation_types", [])[:6],
                "source_paths": payload.get("source_paths", [])[:6],
                "observation_count": payload.get("observation_count"),
                "truncated": item["truncated"],
            })
        prompt_context = {
            "a_baseline": {
                "decision": baseline["decision"],
                "findings": _brief_items(baseline["findings"]),
                "counterevidence": _brief_items(baseline["counterevidence"]),
                "unresolved_questions": _brief_items(baseline["unresolved_questions"]),
                "limitations": _brief_items(baseline["limitations"]),
            },
            "b_graph": {
                "graph_fingerprint": graph_snapshot["graph_fingerprint"],
                "projection_version": graph_snapshot.get("graph_projection_version"),
                "backend": graph_snapshot.get("graph_backend"),
                "node_count": graph_snapshot.get("graph_node_count"),
                "edge_count": graph_snapshot.get("graph_edge_count"),
                "retrieval": graph_retrieval_briefs,
            },
        }
        investigator_problem = (
            "Task: " + task_projection["task"]["title"] + "\\n"
            + task_projection["task"]["problem_statement"] + "\\n"
            + "A/B are machine-generated investigative context, not ground truth. Independently inspect "
              "the pinned source and graph evidence; do not assume their decisions are correct. "
              "Separate observations, inferences, counterevidence and unresolved questions; abstain "
              "when evidence is insufficient. The complete A/B records remain in the request package; "
              "the following is only a compact orientation.\\n"
            + json.dumps(prompt_context, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        )
        # RepositoryInvestigator requires a non-empty target and at least one
        # distinct context path whenever complete context discovery is enabled.
        # B's graph retrieval is not required to have run the C-only trace tool,
        # so derive the deterministic context contract from the same allowlisted
        # declared scope instead of emitting an impossible empty requirement.
        if required_context_target is None:
            required_context_target = python_paths[0]
        required_context_paths = [
            path for path in required_source_paths
            if path != required_context_target
        ]
        if not required_context_paths:
            raise ValueError("C_request_requires_at_least_one_distinct_context_path")

        request = {
            "schema_version": "ae32d/c-request/v1",
            "investigator_problem": investigator_problem,
            "case_id": b_report["case_id"],
            "source_commit_sha": b_report["source_commit_sha"],
            "task_contract_digest": b_report["task_contract_digest"],
            "b_report_sha256": preflight["b_report_sha256"],
            "graph_fingerprint": b_report["graph_snapshot"]["graph_fingerprint"],
            "provider_name": preflight["request_plan"]["provider_name"],
            "model_name": preflight["request_plan"]["model_name"],
            "authorization_id": preflight["request_plan"]["authorization_id"],
            "authorization_sha256": _sha256(canonical_json_bytes(authorization)),
            "prompt_source_sha256": preflight["prompt_source_sha256"],
            "tool_catalog_sha256": preflight["tool_catalog_sha256"],
            "cost_estimator_sha256": preflight["cost_estimator_sha256"],
            "budget": preflight["request_plan"]["budget"],
            "context": context,
            "investigation_requirements": {
                "required_source_paths": required_source_paths,
                "required_graph_target": python_paths[0],
                "required_graph_relation_types": ["CALLS", "DEFINES", "IMPORTS", "INVOKES", "MEMBER_OF", "TESTS"],
                "required_graph_direction": "both",
                "require_graph_interaction": True,
                "require_complete_investigation_context": True,
                "prefetch_required_graph_query": True,
                "required_context_target": required_context_target,
                "required_context_paths": required_context_paths,
                "prefetch_required_context_trace": True,
            },
            "dispatch": {
                "manual_dispatch_confirmed": False,
                "provider_dispatch_permitted": False,
                "provider_calls_attempted": 0,
                "credentials_accessed": False,
            },
        }
        request_digest = _sha256(canonical_json_bytes(request))
        status = "prepared_manual_only"

    output = {
        "schema_version": "ae32d/c-request-package/v1",
        "status": status,
        "preflight": preflight,
        "request": request,
        "request_sha256": request_digest,
        "manual_dispatch_confirmed": False,
        "provider_dispatch_permitted": False,
        "provider_calls_attempted": 0,
        "credentials_accessed": False,
    }
    Draft202012Validator(output_schema).validate(output)
    return output
