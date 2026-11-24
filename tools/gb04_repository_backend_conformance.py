#!/usr/bin/env python3
"""Repository-backed conformance for the selected AE-32C graph backend.

Unlike the E.8.5 in-memory fixture runner, this runner builds the real
controlled repository evidence index, executes backend-backed graph queries,
then follows graph-surfaced paths through the bounded source-read tool and
checks source hashes. It never executes repository code or calls an LLM.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from audit_engine.semantic_audit.ae32b.evidence_tools import RepositoryEvidenceTools  # noqa: E402

DEFAULT_FIXTURE = REPOSITORY_ROOT / "tests/semantic_audit/fixtures/ae32c_provider_interface_incident"
REQUIRED_TARGET = "symbol:pipeline.extractor::extract"
REQUIRED_CALLERS = {"main.py", "tests/checks.py"}


def _unwrap(response: dict[str, Any], tool: str) -> dict[str, Any]:
    if not isinstance(response, dict) or response.get("status") != "ok":
        raise RuntimeError(f"{tool}_failed:{response.get('error_code') if isinstance(response, dict) else 'invalid_response'}")
    result = response.get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"{tool}_result_missing")
    return result


def _runtime(tools: RepositoryEvidenceTools) -> dict[str, Any]:
    return tools.graph_runtime_report()


def _progress(backend: str, phase: str, **details: Any) -> None:
    record = {"backend": backend, "phase": phase, **details}
    print("[E8.8] " + json.dumps(record, sort_keys=True), flush=True)


def _run_repository_conformance_with_tools(
    repo_root: Path,
    backend: str,
    tools: RepositoryEvidenceTools,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    initial_runtime = _runtime(tools)
    if initial_runtime.get("active_computation_backend") != backend:
        raise RuntimeError("selected_backend_not_active")

    summary_response = tools.invoke("repository_summary", {})
    summary = _unwrap(summary_response, "repository_summary")
    summary_provenance = summary_response.get("provenance", {})
    if summary.get("evidence_index_status") != "complete":
        raise RuntimeError("repository_evidence_index_incomplete")
    _progress(
        backend, "repository_index_ready",
        indexed_file_count=summary.get("indexed_file_count"),
        graph_node_count=summary.get("graph_node_count"),
        graph_edge_count=summary.get("graph_edge_count"),
    )

    neighbors = _unwrap(tools.invoke("graph_neighbors", {
        "node": REQUIRED_TARGET,
        "direction": "incoming",
        "relation_types": ["CALLS"],
        "max_depth": 1,
        "max_results": 20,
    }), "graph_neighbors")
    if neighbors.get("coverage_status") != "complete_for_query":
        raise RuntimeError("required_graph_query_incomplete")
    observed = set(neighbors.get("observed_relation_types", []))
    if "CALLS" not in observed:
        raise RuntimeError("required_CALLS_relationship_not_observed")
    source_paths = set(neighbors.get("source_paths", []))
    if not REQUIRED_CALLERS.issubset(source_paths):
        raise RuntimeError("required_repository_source_paths_missing")
    _progress(
        backend, "required_graph_query_complete",
        source_paths=sorted(source_paths),
        observed_relations=sorted(observed),
    )

    # The graph evidence supplies expected source hashes. The source tool is
    # the only authority for reading file content and enforces repository scope.
    expected_hashes: dict[str, set[str]] = {}
    for item in list(neighbors.get("source_nodes", [])) + list(neighbors.get("discovered_nodes", [])):
        if isinstance(item, dict):
            path, digest = item.get("path"), item.get("source_sha256")
            if isinstance(path, str) and isinstance(digest, str):
                expected_hashes.setdefault(path, set()).add(digest)
    for item in neighbors.get("evidence", []):
        if not isinstance(item, dict):
            continue
        provenance = item.get("provenance", {})
        edge_metadata = provenance.get("edge_metadata", {}) if isinstance(provenance, dict) else {}
        path, digest = edge_metadata.get("path"), edge_metadata.get("source_sha256")
        if isinstance(path, str) and isinstance(digest, str):
            expected_hashes.setdefault(path, set()).add(digest)

    reads: list[dict[str, Any]] = []
    for path in sorted(REQUIRED_CALLERS):
        source = tools.contents.get(path)
        if not isinstance(source, str):
            raise RuntimeError(f"graph_surfaced_source_not_indexed:{path}")
        total_lines = len(source.splitlines())
        read_response = tools.invoke("read_source_file", {
            "path": path,
            "start_line": 1,
            "end_line": max(1, total_lines),
        })
        read = _unwrap(read_response, "read_source_file")
        expected = expected_hashes.get(path, set())
        if len(expected) != 1:
            raise RuntimeError(f"graph_source_hash_missing_or_ambiguous:{path}")
        if read.get("source_sha256") != next(iter(expected)):
            raise RuntimeError(f"graph_to_source_hash_mismatch:{path}")
        if read.get("source_range_complete") is not True or read.get("content_omitted") is not False:
            raise RuntimeError(f"graph_surfaced_source_read_incomplete:{path}")
        reads.append({
            "path": path,
            "source_sha256": read.get("source_sha256"),
            "source_range_complete": read.get("source_range_complete"),
            "line_count": total_lines,
        })
    _progress(backend, "source_hash_followthrough_complete", verified_read_count=len(reads))

    # Exercise the other backend-backed graph operations against the same
    # repository snapshot and preserve their independent evidence outputs.
    main_symbol = next((
        node.node_id for node in tools.graph.nodes
        if node.entity_type == "PythonSymbol"
        and node.attributes.get("path") == "main.py"
        and node.attributes.get("name") == "main"
    ), None)
    target_symbol = tools._resolve_node(REQUIRED_TARGET)
    if not main_symbol:
        raise RuntimeError("repository_entrypoint_symbol_missing")
    path_result = _unwrap(tools.invoke("graph_path", {
        "source": main_symbol,
        "target": target_symbol,
        "direction": "outgoing",
        "relation_types": ["CALLS"],
        "max_depth": 2,
    }), "graph_path")
    if path_result.get("path_found") is not True:
        raise RuntimeError("repository_graph_path_not_found")
    _progress(backend, "graph_path_complete", path_step_count=len(path_result.get("path", [])))

    related_tests = _unwrap(tools.invoke("find_related_tests", {
        "target": "pipeline/extractor.py",
        "max_results": 20,
    }), "find_related_tests")
    if related_tests.get("coverage_status") != "complete_for_query":
        raise RuntimeError("related_test_discovery_incomplete")
    _progress(backend, "related_test_discovery_complete", returned_count=related_tests.get("returned_count"))

    # Context tools must execute local adjacency through the selected NetworkX
    # projection. The nested workflow query is attributed to trace execution.
    trace_context = _unwrap(tools.invoke("trace_execution_context", {
        "target": "pipeline/extractor.py",
        "max_depth": 4,
        "max_results": 20,
    }), "trace_execution_context")
    workflow_context = _unwrap(tools.invoke("find_workflow_context", {
        "target": "pipeline/extractor.py",
        "max_results": 20,
    }), "find_workflow_context")
    _progress(
        backend, "context_traversals_complete",
        traversal_queries=execution.get("queries_attempted"),
        trace_adjacency_queries=trace_telemetry.get("adjacency_queries_attempted"),
        workflow_adjacency_queries=workflow_telemetry.get("adjacency_queries_attempted"),
    )

    final_runtime = _runtime(tools)
    execution = final_runtime.get("backend_execution", {})
    context_telemetry = final_runtime.get("context_operation_telemetry", {})
    trace_telemetry = context_telemetry.get("trace_execution_context", {})
    nested_telemetry = context_telemetry.get("trace_execution_context.workflow_context", {})
    workflow_telemetry = context_telemetry.get("find_workflow_context", {})
    context_backend_execution = final_runtime.get(
        "backend_native_query_mode", "backend_native_query_mode_unreported"
    )
    if execution.get("parity_failures", 0) != 0:
        raise RuntimeError("backend_reference_parity_failure")
    if execution.get("parity_verified_queries", 0) < 3:
        raise RuntimeError("insufficient_backend_parity_verified_queries")
    if final_runtime.get("context_backend_bypass_count", 0) != 0:
        raise RuntimeError("context_tool_backend_bypass_detected")
    for operation, telemetry in (
        ("trace_execution_context", trace_telemetry),
        ("trace_execution_context.workflow_context", nested_telemetry),
        ("find_workflow_context", workflow_telemetry),
    ):
        if telemetry.get("adjacency_queries_attempted", 0) < 1:
            raise RuntimeError(f"{operation}_native_adjacency_not_observed")
        if telemetry.get("adjacency_queries_failed", 0) != 0:
            raise RuntimeError(f"{operation}_native_adjacency_failure")
        if telemetry.get("parity_failures", 0) != 0:
            raise RuntimeError(f"{operation}_reference_parity_failure")
        if telemetry.get("parity_verified", 0) < 1:
            raise RuntimeError(f"{operation}_reference_parity_not_verified")
        if telemetry.get("native_adjacency_lookups", 0) < 1:
            raise RuntimeError(f"{operation}_native_adjacency_not_used")

    return {
        "schema_version": "ae32c/repository-backend-conformance/v1",
        "status": "passed",
        "backend": backend,
        "source_revision": os.environ.get("AE32C_SOURCE_REVISION"),
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
        "workflow_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "workflow_name": os.environ.get("GITHUB_WORKFLOW"),
        "backend_library": final_runtime.get("backend_library"),
        "backend_library_version": final_runtime.get("backend_library_version"),
        "backend_native_query_mode": final_runtime.get("backend_native_query_mode"),
        "native_worker": final_runtime.get("backend_worker_info"),
        "repository_snapshot": {
            "evidence_index_status": summary.get("evidence_index_status"),
            "indexed_file_count": summary.get("indexed_file_count"),
            "graph_node_count": summary.get("graph_node_count"),
            "graph_edge_count": summary.get("graph_edge_count"),
            "graph_fingerprint": summary.get("graph_fingerprint"),
            "source_manifest_sha256": summary_provenance.get("source_manifest_sha256") if isinstance(summary_provenance, dict) else None,
        },
        "backend_queries": {
            "graph_neighbors": "selected_backend_and_reference_parity_verified",
            "graph_path": "selected_backend_and_reference_parity_verified",
            "find_related_tests": "selected_backend_and_reference_parity_verified",
            "trace_execution_context": {
                "status": trace_context.get("coverage_status"),
                "backend_execution": context_backend_execution,
                "telemetry": trace_telemetry,
            },
            "trace_nested_find_workflow_context": {
                "backend_execution": context_backend_execution,
                "telemetry": nested_telemetry,
            },
            "find_workflow_context": {
                "status": workflow_context.get("coverage_status"),
                "backend_execution": context_backend_execution,
                "telemetry": workflow_telemetry,
            },
        },
        "required_graph_query": {
            "target": REQUIRED_TARGET,
            "direction": "incoming",
            "relations": sorted(observed),
            "source_paths": sorted(source_paths),
            "coverage_status": neighbors.get("coverage_status"),
        },
        "graph_to_repository_follow_through": {
            "status": "passed",
            "verified_read_count": len(reads),
            "reads": reads,
        },
        "graph_path": {
            "path_found": path_result.get("path_found"),
            "step_count": len(path_result.get("path", [])),
            "relations": sorted({str(item.get("relation")) for item in path_result.get("path", [])}),
        },
        "related_tests": {
            "candidate_count": related_tests.get("candidate_count"),
            "returned_count": related_tests.get("returned_count"),
            "paths": sorted({item.get("path") for item in related_tests.get("tests", []) if isinstance(item, dict)}),
        },
        "backend_execution": final_runtime.get("backend_execution"),
        # Context-tool counters are maintained by RepositoryEvidenceTools,
        # separately from traversal-engine counters. Keep them explicit in
        # the conformance artifact instead of nesting them under
        # backend_execution (which only describes traversal-engine metrics).
        "context_operation_telemetry": context_telemetry,
        "side_effects": {
            "repository_code_executed": False,
            "tests_executed_by_backend": False,
            "source_files_modified": False,
            "network_calls_performed": False,
            "provider_calls_made": False,
        },
        "limitations": [
            "This runner validates backend graph queries over the repository-derived semantic graph and hash-bound source reads; it does not execute repository code.",
            "A passing repository conformance run does not establish diagnostic correctness or live LLM tool-selection quality.",
        ],
    }


def run_repository_conformance(repo_root: Path, backend: str) -> dict[str, Any]:
    """Run repository-backed conformance with deterministic backend teardown."""
    resolved_root = repo_root.resolve()
    tools = RepositoryEvidenceTools(resolved_root, graph_backend=backend)
    _progress(backend, "repository_tools_initialized")
    try:
        report = _run_repository_conformance_with_tools(
            resolved_root, backend, tools,
        )
        return report
    finally:
        _progress(backend, "closing_backend_resources")
        tools.close()
        _progress(backend, "backend_resources_closed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", default="networkx", choices=("networkx", "scipy", "igraph", "graph-tool", "snap"))
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", type=Path, default=Path("gb04-repository-backend-conformance.json"))
    args = parser.parse_args()
    try:
        report = run_repository_conformance(args.repo_root, args.backend)
        exit_code = 0
    except Exception as exc:
        report = {
            "schema_version": "ae32c/repository-backend-conformance/v1",
            "status": "failed",
            "backend": args.backend,
            "failure_type": type(exc).__name__,
            "failure_message": str(exc)[:1000],
            "provider_calls_made": False,
        }
        exit_code = 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
