"""AE-32C runtime architecture and graph-backend observability.

This module reports which components are wired into the current investigation
path. It deliberately distinguishes installed/available graph libraries from
backends actually used by AE-32B/AE-32C.
"""
from __future__ import annotations

import importlib.util
from typing import Any, Mapping, Iterable

from audit_engine.semantic_audit.ae32c.tool_policy import GRAPH_DERIVED_TOOL_NAMES

SCHEMA_VERSION = "ae32c/runtime-architecture/v2"

_BACKEND_MODULES = {
    "networkx": "networkx",
    "scipy": "scipy",
    "igraph": "igraph",
    "graph-tool": "graph_tool",
    "snap": "snap",
}


def _available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _safe_nonnegative(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value < 0:
        return None
    return value


def build_runtime_architecture_report(
    *,
    audit_report: Mapping[str, Any],
    repository_summary: Mapping[str, Any],
    provider_name: str = "unknown",
    model_name: str = "unknown",
    provider_stats: Mapping[str, Any] | None = None,
    available_tool_names: Iterable[str] = (),
    graph_runtime: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe the current AE-32C execution path without making network calls."""
    audit = audit_report.get("audit", {}) if isinstance(audit_report.get("audit"), Mapping) else {}
    call_graph = repository_summary.get("call_graph", {})
    if not isinstance(call_graph, Mapping):
        call_graph = {}
    relations = repository_summary.get("graph_relation_counts", {})
    if not isinstance(relations, Mapping):
        relations = {}
    tools = sorted({item for item in available_tool_names if isinstance(item, str)})
    stats = provider_stats if isinstance(provider_stats, Mapping) else {}
    usage = stats.get("usage", {}) if isinstance(stats.get("usage"), Mapping) else {}
    runtime = graph_runtime if isinstance(graph_runtime, Mapping) else repository_summary.get("graph_runtime", {})
    if not isinstance(runtime, Mapping):
        runtime = {}
    active_backend = str(runtime.get("active_computation_backend", "python_reference_traversal"))
    active_algorithm = str(runtime.get("active_traversal_algorithm", "deterministic_breadth_first_search"))
    active_adapters = runtime.get("external_backend_adapters_active", [])
    if not isinstance(active_adapters, (list, tuple)):
        active_adapters = []
    active_adapters = sorted({str(item) for item in active_adapters if isinstance(item, str)})
    backend_execution = runtime.get("backend_execution", {})
    if not isinstance(backend_execution, Mapping):
        backend_execution = {}

    adapters = {}
    for adapter, module_name in _BACKEND_MODULES.items():
        adapters[adapter] = {
            "adapter_implementation_present": True,
            "library_available_in_runtime": _available(module_name),
            "active_in_ae32b_query_path": adapter in active_adapters or adapter == active_backend,
        }

    if active_backend == "networkx":
        interpretation = (
            "AE-32B graph queries use the canonical SemanticGraph as source of truth and a "
            "NetworkX MultiDiGraph projection for indexed directed multigraph adjacency. "
            "AE-32 deterministic BFS controls ordering, bounds and evidence construction; "
            "each accepted query is compared with the pure-Python reference traversal."
        )
    elif active_backend == "python_reference_traversal":
        interpretation = (
            "AE-32B graph queries use the canonical SemanticGraph and the pure-Python "
            "deterministic BFS reference traversal; external graph adapters are not active."
        )
    else:
        interpretation = (
            "AE-32B graph queries report a configured computation backend. Inspect backend "
            "execution provenance and parity status before interpreting results."
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "source_snapshot": {
            "audit_status": audit.get("status", "unknown"),
            "manifest_sha256": audit.get("manifest_sha256"),
            "included_file_count": audit.get("included_file_count"),
            "python_file_count": audit.get("python_file_count"),
            "python_parse_issue_count": audit.get("python_parse_issue_count"),
            "scope_issue_count": audit.get("scope_issue_count"),
            "repository_code_executed_by_scanner": False,
        },
        "audit_engine": {
            "deterministic_scanner": "AE-32A.audit_repository",
            "mode": "static_ast_import_workflow_and_source_inventory",
            "static_finding_count": repository_summary.get("static_finding_count"),
            "python_parse_issue_count": repository_summary.get("python_parse_issue_count"),
            "scope_issue_count": repository_summary.get("scope_issue_count"),
            "executes_target_repository_code": False,
        },
        "graph_engine": {
            "canonical_semantic_model": "SemanticGraph",
            "query_service": "SemanticGraphAnalysisService",
            "traversal_engine": "GraphTraversalEngine",
            "active_algorithm": active_algorithm,
            "active_computation_backend": active_backend,
            "backend_library": runtime.get("backend_library"),
            "backend_library_version": runtime.get("backend_library_version"),
            "backend_projection_type": runtime.get("backend_projection_type"),
            "backend_projection_fingerprint": runtime.get("backend_projection_fingerprint"),
            "backend_parity_mode": runtime.get("backend_parity_mode"),
            "backend_execution": dict(backend_execution),
            "backend_pipeline": runtime.get("backend_pipeline"),
            "backend_pipeline_provenance": runtime.get("backend_pipeline_provenance", []),
            "backend_pipeline_transformations": runtime.get("backend_pipeline_transformations", []),
            "external_backend_adapters_active": active_adapters,
            "graph_node_count": repository_summary.get("graph_node_count"),
            "graph_edge_count": repository_summary.get("graph_edge_count"),
            "graph_relation_counts": dict(sorted((str(k), int(v)) for k, v in relations.items()
                                                   if isinstance(v, int) and not isinstance(v, bool))),
            "graph_fingerprint": repository_summary.get("graph_fingerprint"),
            "graph_projection_version": repository_summary.get("graph_projection_version"),
            "call_graph": {
                "candidate_call_sites": call_graph.get("candidate_call_sites"),
                "resolved_call_edge_occurrences": call_graph.get("resolved_call_edges"),
                "unresolved_call_sites": call_graph.get("unresolved_call_sites"),
                "ambiguous_call_sites": call_graph.get("ambiguous_call_sites"),
                "resolution_policy": call_graph.get("resolution_policy"),
                "runtime_execution": False,
            },
            "backend_adapter_boundary_present": True,
            "backend_pipeline_wired_into_ae32b_query_path": bool(
                runtime.get("backend_pipeline_wired_into_ae32b_query_path", active_backend != "python_reference_traversal")
            ),
            "external_backend_adapters": adapters,
            "rdflib_available": _available("rdflib"),
            "rdflib_role": "RDF representation/interchange support; not the active traversal backend",
            "interpretation": interpretation,
        },
        "llm_driver": {
            "provider": str(provider_name)[:100],
            "model": str(model_name)[:200],
            "credential_source": "environment variable populated locally or by GitHub Actions secrets",
            "credential_value_in_report": False,
            "requests_attempted": _safe_nonnegative(stats.get("logical_calls")),
            "prompt_tokens": _safe_nonnegative(usage.get("prompt_tokens")),
            "completion_tokens": _safe_nonnegative(usage.get("completion_tokens")),
            "total_tokens": _safe_nonnegative(usage.get("total_tokens")),
            "reported_cost_usd": _safe_nonnegative(usage.get("reported_cost_usd")),
        },
        "investigation_tools": {
            "available_tool_names": tools,
            "available_tool_count": len(tools),
            "graph_derived_tool_names": sorted(GRAPH_DERIVED_TOOL_NAMES),
            "graph_derived_tool_count": len(GRAPH_DERIVED_TOOL_NAMES),
            "tool_execution_boundary": "trusted AE-32B dispatcher; validated arguments; read-only evidence operations",
        },
        "deterministic_action_boundary": {
            "model_selects_from_registered_evidence_tools": True,
            "model_can_execute_shell_commands": False,
            "model_can_execute_repository_code": False,
            "model_can_modify_repository_files": False,
            "model_can_apply_patches_or_commit": False,
            "registered_verification_orchestration_present": True,
            "registered_verification_orchestration_invoked_by_ae32c": False,
            "high_assurance_registered_witness_layer_present": True,
            "high_assurance_witness_layer_invoked_by_ae32c": False,
            "deterministic_follow_up_plan_mode": "plan_only",
            "arbitrary_model_supplied_actions_permitted": False,
        },
        "claims_boundary": {
            "static_graph_relationships_are_runtime_execution_proof": False,
            "source_line_linkage_is_semantic_entailment_proof": False,
            "diagnostic_accuracy_assessed_by_this_report": False,
        },
    }
