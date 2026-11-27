"""Deterministic AE-32D condition B: condition A plus bounded AE-32B graph retrieval.

The graph is constructed from a temporary copy of only the declared fixture files.
The selected NetworkX traversal adapter is used because this condition requires
bounded adjacency and path queries; this is a task-relevance choice, not a
performance ranking. Graph evidence is additive and does not yet alter A's
decision: no graph-specific diagnostic rule is enabled in B v0.1.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from audit_engine.semantic_audit.ae32b.evidence_tools import RepositoryEvidenceTools
from tools.ae32d_deterministic_audit import (
    ADAPTER_REVISION as A_ADAPTER_REVISION,
    REPORT_SCHEMA,
    ROOT,
    _canonical_digest,
    _git_head,
    _read_scope_file,
    _resolve_fixture_root,
    _scope_relative_path,
    run_deterministic_audit,
)
from tools.ae32d_trial_contracts import canonical_json_bytes

B_ADAPTER_REVISION = "ae32d-deterministic-b/0.1.0"
GRAPH_BACKEND = "networkx"
RELATION_TYPES = ["CALLS", "DEFINES", "IMPORTS", "INVOKES", "MEMBER_OF", "TESTS"]
GRAPH_POLICY = {
    "version": "ae32d-b-retrieval/0.1.0",
    "backend": GRAPH_BACKEND,
    "file_neighbors": {
        "direction": "both", "relation_types": RELATION_TYPES, "max_depth": 1, "max_results": 16,
    },
    "symbol_search": {"kind": "function", "max_results": 8},
    "symbol_neighbors": {
        "direction": "both", "relation_types": ["CALLS", "INVOKES", "MEMBER_OF", "TESTS"],
        "max_depth": 1, "max_results": 12,
    },
    "symbol_path": {"direction": "outgoing", "relation_types": ["DEFINES"], "max_depth": 2},
    "related_tests": {"max_results": 10},
    "execution_context": {"max_depth": 2, "max_results": 10},
    "max_python_files": 16,
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _runner_revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        capture_output=True, text=True, timeout=10,
    )
    return result.stdout.strip()


def _scope_snapshot(task_projection: dict[str, Any], source_root: Path, destination: Path) -> list[str]:
    fixture_root = _resolve_fixture_root(source_root, task_projection["source"]["fixture_path"])
    missing: list[str] = []
    copied: list[dict[str, Any]] = []
    descriptors: list[str] = []
    unreadable: list[str] = []
    for item in task_projection["task"]["declared_scope"]:
        relative = _scope_relative_path(item, task_projection["source"]["fixture_path"])
        if relative is None:
            descriptors.append(item)
            continue
        try:
            data, _ = _read_scope_file(fixture_root, relative)
        except FileNotFoundError:
            missing.append(relative)
            continue
        except (OSError, ValueError):
            unreadable.append(relative)
            continue
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            unreadable.append(relative)
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        copied.append({"path": relative, "size": len(data), "sha256": _sha256(data)})
    snapshot_digest = _canonical_digest({
        "files": sorted(copied, key=lambda row: row["path"]),
        "missing_paths": sorted(missing),
        "unreadable_paths": sorted(unreadable),
        "scope_descriptors": sorted(descriptors),
    })
    return {"digest": snapshot_digest, "issues": missing + unreadable, "file_count": len(copied)}


def _tool_record(tool: str, arguments: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    result = response.get("result", {})
    return {
        "tool": tool,
        "arguments": arguments,
        "status": response.get("status", "error"),
        "coverage_status": result.get("coverage_status", "unknown") if isinstance(result, dict) else "unknown",
        "truncated": bool(result.get("truncated", False)) if isinstance(result, dict) else False,
        "response_digest": _sha256(canonical_json_bytes(response)),
        "payload": result if isinstance(result, dict) else {},
        **({"error_code": response.get("error", {}).get("code", "unknown_error")}
           if response.get("status") != "ok" else {}),
    }


def run_graph_assisted_audit(task_projection: dict[str, Any], source_root: str | Path) -> dict[str, Any]:
    """Run A unchanged, then append deterministic graph evidence from the same pinned scope."""
    schema = json.loads(REPORT_SCHEMA.read_text(encoding="utf-8"))
    if task_projection.get("condition") != "B_graph":
        raise ValueError("condition_B_requires_B_graph_projection")

    root = Path(source_root).resolve(strict=True)
    actual_sha = _git_head(root)
    if actual_sha != task_projection["source"]["source_commit_sha"]:
        raise ValueError("source_revision_mismatch:" + actual_sha)

    baseline_projection = dict(task_projection)
    baseline_projection["condition"] = "A_deterministic"
    baseline_report = run_deterministic_audit(baseline_projection, root)

    retrieval_records: list[dict[str, Any]] = []
    execution_trace = list(baseline_report["execution_trace"])
    graph_truncated = False
    graph_errors = False

    with tempfile.TemporaryDirectory(prefix="ae32d-b-scope-") as temporary:
        graph_root = Path(temporary)
        scope_snapshot = _scope_snapshot(task_projection, root, graph_root)
        if scope_snapshot["issues"]:
            raise ValueError("graph_scope_snapshot_failed:" + ",".join(scope_snapshot["issues"]))
        if scope_snapshot["digest"] != baseline_report["source_manifest_digest"]:
            raise ValueError("graph_scope_snapshot_does_not_match_A_manifest")
        if _git_head(root) != actual_sha:
            raise ValueError("source_revision_changed_during_B_snapshot")

        evidence_tools = RepositoryEvidenceTools(
            graph_root,
            source_revision=actual_sha,
            runner_revision=_runner_revision(),
            graph_backend=GRAPH_BACKEND,
        )
        try:
            def invoke(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
                nonlocal graph_truncated, graph_errors
                response = evidence_tools.invoke(tool, arguments)
                record = _tool_record(tool, arguments, response)
                retrieval_records.append(record)
                graph_truncated = graph_truncated or record["truncated"] or record["coverage_status"] == "partial"
                graph_errors = graph_errors or record["status"] != "ok"
                execution_trace.append({
                    "step_id": "B-" + str(len(retrieval_records)),
                    "operation": "ae32b_" + tool,
                    "status": "error" if record["status"] != "ok" else (
                        "partial" if record["truncated"] or record["coverage_status"] == "partial" else "ok"
                    ),
                    "details": {
                        "arguments": arguments,
                        "response_digest": record["response_digest"],
                        "coverage_status": record["coverage_status"],
                        "truncated": record["truncated"],
                    },
                })
                return response

            summary = invoke("repository_summary", {})
            if summary.get("status") != "ok":
                raise ValueError("graph_repository_summary_failed")
            summary_result = summary.get("result", {})
            provenance = summary.get("provenance", {})
            runtime = summary_result.get("graph_runtime", {})
            evidence_index_status = summary_result.get("evidence_index_status", "incomplete")
            graph_snapshot = {
                "status": "complete" if evidence_index_status == "complete" else "incomplete",
                "source_revision": actual_sha,
                "source_manifest_sha256": provenance.get("source_manifest_sha256"),
                "graph_fingerprint": provenance.get("graph_fingerprint"),
                "graph_projection_version": provenance.get("graph_projection_version"),
                "evidence_index_status": evidence_index_status,
                "graph_backend": runtime.get("active_computation_backend", "unknown"),
                "graph_node_count": summary_result.get("graph_node_count", 0),
                "graph_edge_count": summary_result.get("graph_edge_count", 0),
                "backend_pipeline_wired": bool(runtime.get("backend_pipeline_wired_into_ae32b_query_path", False)),
            }
            if not graph_snapshot["source_manifest_sha256"] or not graph_snapshot["graph_fingerprint"] or not graph_snapshot["graph_projection_version"]:
                raise ValueError("graph_snapshot_provenance_incomplete")

            python_paths = sorted(
                path for path in (
                    _scope_relative_path(item, task_projection["source"]["fixture_path"])
                    for item in task_projection["task"]["declared_scope"]
                )
                if path and path.endswith(".py")
            )[:GRAPH_POLICY["max_python_files"]]

            for path in python_paths:
                invoke("graph_neighbors", {
                    "node": path,
                    "direction": GRAPH_POLICY["file_neighbors"]["direction"],
                    "relation_types": GRAPH_POLICY["file_neighbors"]["relation_types"],
                    "max_depth": GRAPH_POLICY["file_neighbors"]["max_depth"],
                    "max_results": GRAPH_POLICY["file_neighbors"]["max_results"],
                })

            # Symbol lookup is deterministic and bounded. Function name comes only
            # from the task-visible expected-behavior contract in the A scope.
            expected_path = _scope_relative_path("expected_behavior.json", task_projection["source"]["fixture_path"])
            function_name = None
            if expected_path and (graph_root / expected_path).is_file():
                try:
                    contract = json.loads((graph_root / expected_path).read_text(encoding="utf-8"))
                    function_name = contract.get("function") if isinstance(contract.get("function"), str) else None
                except (OSError, json.JSONDecodeError):
                    function_name = None
            if function_name:
                symbols_response = invoke("search_symbols", {
                    "query": function_name,
                    "kind": GRAPH_POLICY["symbol_search"]["kind"],
                    "max_results": GRAPH_POLICY["symbol_search"]["max_results"],
                })
                symbols = symbols_response.get("result", {}).get("symbols", [])
                for symbol in sorted(symbols, key=lambda row: (row.get("path", ""), row.get("line", 0), row.get("node_id", ""))):
                    if symbol.get("path") not in python_paths:
                        continue
                    node_id = symbol.get("node_id")
                    if not isinstance(node_id, str):
                        continue
                    invoke("graph_neighbors", {
                        "node": node_id,
                        "direction": GRAPH_POLICY["symbol_neighbors"]["direction"],
                        "relation_types": GRAPH_POLICY["symbol_neighbors"]["relation_types"],
                        "max_depth": GRAPH_POLICY["symbol_neighbors"]["max_depth"],
                        "max_results": GRAPH_POLICY["symbol_neighbors"]["max_results"],
                    })
                    invoke("graph_path", {
                        "source": symbol["path"],
                        "target": node_id,
                        "direction": GRAPH_POLICY["symbol_path"]["direction"],
                        "relation_types": GRAPH_POLICY["symbol_path"]["relation_types"],
                        "max_depth": GRAPH_POLICY["symbol_path"]["max_depth"],
                    })

            scope_descriptors = task_projection["task"]["declared_scope"]
            if any("related tests" in item.casefold() for item in scope_descriptors):
                for path in python_paths:
                    invoke("find_related_tests", {
                        "target": path,
                        "max_results": GRAPH_POLICY["related_tests"]["max_results"],
                    })

            task_text = task_projection["task"]["problem_statement"].casefold()
            if "runtime" in task_text or "workflow" in task_text or "entrypoint" in task_text:
                for path in python_paths[:1]:
                    invoke("trace_execution_context", {
                        "target": path,
                        "max_depth": GRAPH_POLICY["execution_context"]["max_depth"],
                        "max_results": GRAPH_POLICY["execution_context"]["max_results"],
                    })
        finally:
            evidence_tools.close()
    if _git_head(root) != actual_sha:
        raise ValueError("source_revision_changed_during_B_retrieval")

    graph_policy_digest = _canonical_digest(GRAPH_POLICY)
    baseline_config_digest = baseline_report["config_digest"]
    b_config_digest = _canonical_digest({
        "adapter_revision": B_ADAPTER_REVISION,
        "baseline_config_digest": baseline_config_digest,
        "graph_policy_digest": graph_policy_digest,
        "graph_snapshot_fingerprint": graph_snapshot["graph_fingerprint"],
        "graph_backend": GRAPH_BACKEND,
        "runner_source_sha256": _sha256(Path(__file__).read_bytes()),
        "ae32b_tool_source_sha256": _sha256((ROOT / "audit_engine" / "semantic_audit" / "ae32b" / "evidence_tools.py").read_bytes()),
    })
    graph_incomplete = graph_snapshot["status"] != "complete" or not graph_snapshot["backend_pipeline_wired"]
    status = "completed" if baseline_report["status"] == "completed" and not graph_truncated and not graph_errors and not graph_incomplete else "partial"
    report = {
        "schema_version": "ae32d/condition-report/v1",
        "case_id": baseline_report["case_id"],
        "condition": "B_graph",
        "adapter_revision": B_ADAPTER_REVISION,
        "source_commit_sha": baseline_report["source_commit_sha"],
        "task_contract_digest": baseline_report["task_contract_digest"],
        "config_digest": b_config_digest,
        "source_manifest_digest": baseline_report["source_manifest_digest"],
        "status": status,
        "coverage": {
            "declared_scope_complete": baseline_report["coverage"]["declared_scope_complete"],
            "truncated": baseline_report["coverage"]["truncated"] or graph_truncated,
            "unreadable_paths": baseline_report["coverage"]["unreadable_paths"],
            "missing_paths": baseline_report["coverage"]["missing_paths"],
        },
        "findings": baseline_report["findings"],
        "counterevidence": baseline_report["counterevidence"],
        "unresolved_questions": baseline_report["unresolved_questions"],
        "decision": baseline_report["decision"],
        "limitations": list(baseline_report["limitations"]),
        "execution_trace": execution_trace,
        "baseline_report": baseline_report,
        "baseline_config_digest": baseline_config_digest,
        "graph_snapshot": graph_snapshot,
        "graph_retrieval": retrieval_records,
    }
    if graph_incomplete:
        report["limitations"].append("graph_snapshot_or_backend_incomplete")
    if graph_truncated:
        report["limitations"].append("graph_retrieval_truncated")
    if graph_errors:
        report["limitations"].append("graph_retrieval_error")
    Draft202012Validator(schema).validate(report)
    return report
