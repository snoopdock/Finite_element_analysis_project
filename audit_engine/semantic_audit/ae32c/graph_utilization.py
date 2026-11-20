"""Deterministic, privacy-bounded telemetry for AE-32C graph-assisted investigations.

This module measures observed tool use and evidence follow-through. It does not
score diagnostic correctness or infer causal benefit from graph availability.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any
import math

from audit_engine.semantic_audit.ae32c.tool_policy import GRAPH_DERIVED_TOOL_NAMES

GRAPH_QUERY_TOOL_NAMES = frozenset({"graph_neighbors", "graph_path"})


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _strings(value: Any) -> set[str]:
    if not isinstance(value, (list, tuple, set)):
        return set()
    return {item for item in value if isinstance(item, str) and item}


def _bounded_count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _entry_result(entry: Any) -> Mapping[str, Any]:
    response = _mapping(_get(entry, "response", {}))
    return _mapping(response.get("result"))


def _path_hashes(result: Mapping[str, Any]) -> dict[str, set[str]]:
    hashes: dict[str, set[str]] = {}
    nodes = list(result.get("source_nodes", [])) + list(result.get("discovered_nodes", []))
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        path = node.get("path")
        digest = node.get("source_sha256")
        if isinstance(path, str) and path and isinstance(digest, str) and len(digest) == 64:
            hashes.setdefault(path, set()).add(digest)
    for evidence in result.get("evidence", []):
        if not isinstance(evidence, Mapping):
            continue
        provenance = _mapping(evidence.get("provenance"))
        metadata = _mapping(provenance.get("edge_metadata"))
        path = metadata.get("path")
        digest = metadata.get("source_sha256")
        if isinstance(path, str) and path and isinstance(digest, str) and len(digest) == 64:
            hashes.setdefault(path, set()).add(digest)
    return hashes


def _source_paths(result: Mapping[str, Any]) -> set[str]:
    paths = _strings(result.get("source_paths"))
    for node in list(result.get("source_nodes", [])) + list(result.get("discovered_nodes", [])):
        if isinstance(node, Mapping) and isinstance(node.get("path"), str) and node.get("path"):
            paths.add(node["path"])
    for evidence in result.get("evidence", []):
        if not isinstance(evidence, Mapping):
            continue
        metadata = _mapping(_mapping(evidence.get("provenance")).get("edge_metadata"))
        path = metadata.get("path")
        if isinstance(path, str) and path:
            paths.add(path)
    for candidate in result.get("impact_candidates", []):
        if not isinstance(candidate, Mapping):
            continue
        node = _mapping(candidate.get("node"))
        path = node.get("path") or candidate.get("path")
        if isinstance(path, str) and path:
            paths.add(path)
    return paths


def _discovery_paths_and_hashes(tool: str, result: Mapping[str, Any]) -> tuple[set[str], dict[str, set[str]]]:
    """Extract only explicit path/hash pairs surfaced by registered graph-derived tools."""
    if tool in GRAPH_QUERY_TOOL_NAMES:
        return _source_paths(result), _path_hashes(result)

    paths: set[str] = set()
    hashes: dict[str, set[str]] = {}

    def add(item: Any) -> None:
        if isinstance(item, str) and item:
            paths.add(item)
            return
        if not isinstance(item, Mapping):
            return
        path = item.get("path")
        digest = item.get("source_sha256")
        if isinstance(path, str) and path:
            paths.add(path)
            if isinstance(digest, str) and len(digest) == 64:
                hashes.setdefault(path, set()).add(digest)

    if tool == "trace_execution_context":
        for key in (
            "static_caller_paths", "static_dependency_paths",
            "python_entrypoint_paths", "entrypoint_context_paths",
            "active_workflow_paths",
        ):
            for item in result.get(key, []) if isinstance(result.get(key, []), list) else []:
                add(item)
        for key in ("static_caller_relationships", "static_dependency_relationships", "entrypoint_context_relationships"):
            for item in result.get(key, []) if isinstance(result.get(key, []), list) else []:
                add(item)
    elif tool == "find_related_tests":
        for item in result.get("tests", []) if isinstance(result.get("tests", []), list) else []:
            # The tool can also return text-reference candidates. Only explicit
            # static-import relationships are graph-surfaced paths.
            if isinstance(item, Mapping) and item.get("relationship") == "static_import":
                add(item)
    elif tool == "find_workflow_context":
        for item in result.get("workflows", []) if isinstance(result.get("workflows", []), list) else []:
            add(item)
    return paths, hashes


def _complete_source_read(result: Mapping[str, Any]) -> bool:
    if result.get("source_range_complete") is not True or result.get("content_omitted") is not False:
        return False
    requested_start = result.get("requested_start_line", result.get("start_line"))
    requested_end = result.get("requested_end_line", result.get("end_line"))
    returned_start = result.get("start_line")
    returned_end = result.get("end_line")
    total_lines = result.get("total_lines")
    values = (requested_start, requested_end, returned_start, returned_end, total_lines)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        return False
    if requested_start < 1 or requested_end < requested_start or returned_start != requested_start:
        return False
    expected_end = min(requested_end, total_lines)
    if returned_end < expected_end:
        return False
    if result.get("truncated") is True and not (
        result.get("end_clamped_to_eof") is True and returned_end == total_lines
    ):
        return False
    return True


def _runtime_backend(runtime_architecture: Any) -> dict[str, Any]:
    graph = _mapping(_mapping(runtime_architecture).get("graph_engine"))
    execution = _mapping(graph.get("backend_execution"))
    result: dict[str, Any] = {}
    for key in (
        "active_computation_backend",
        "backend_library",
        "backend_library_version",
        "backend_projection_type",
        "backend_parity_mode",
        "backend_semantic_query_preservation",
    ):
        value = graph.get(key)
        if isinstance(value, str) and len(value) <= 160:
            result[key] = value
    for key in (
        "queries_attempted",
        "queries_succeeded",
        "queries_failed",
        "parity_verified_queries",
        "parity_failures",
        "total_examined_edges",
        "total_visited_nodes",
    ):
        value = _bounded_count(execution.get(key))
        if value is not None:
            result[key] = value
    result["external_backend_adapters_active"] = sorted(_strings(graph.get("external_backend_adapters_active")))
    result["backend_pipeline_wired_into_ae32b_query_path"] = (
        graph.get("backend_pipeline_wired_into_ae32b_query_path")
        if isinstance(graph.get("backend_pipeline_wired_into_ae32b_query_path"), bool)
        else None
    )
    return result


def build_graph_utilization_assessment(
    *,
    ledger_entries: Sequence[Any],
    graph_tools_enabled: bool,
    graph_derived_tools_enabled: bool,
    claim_evidence_assessment: Any = None,
    runtime_architecture: Any = None,
    budget: Any = None,
) -> dict[str, Any]:
    """Measure observed graph-tool use, source follow-through, claim linkage and cost.

    The ledger is authoritative for invocation order and tool results. No prompt,
    model response body, credential, or source contents are copied into this report.
    """
    entries = list(ledger_entries) if isinstance(ledger_entries, Sequence) else []
    usage: dict[str, dict[str, Any]] = {}
    for name in sorted(GRAPH_DERIVED_TOOL_NAMES):
        selected = [item for item in entries if _get(item, "tool") == name]
        usage[name] = {
            "attempt_count": len(selected),
            "successful_call_count": sum(_get(item, "status") == "ok" for item in selected),
            "failed_call_count": sum(_get(item, "status") != "ok" for item in selected),
        }

    graph_queries: list[dict[str, Any]] = []
    query_modes: Counter[str] = Counter()
    relation_types: set[str] = set()
    surfaced: dict[str, dict[str, Any]] = {}
    graph_tool_evidence_ids: set[str] = {
        str(_get(item, "evidence_id"))
        for item in entries
        if _get(item, "tool") in GRAPH_DERIVED_TOOL_NAMES
        and _get(item, "status") == "ok"
        and isinstance(_get(item, "evidence_id"), str)
        and _get(item, "evidence_id")
    }
    query_attempts = query_successes = query_complete = query_partial = query_failed = query_truncated = 0

    for index, entry in enumerate(entries):
        tool = _get(entry, "tool")
        if tool not in GRAPH_QUERY_TOOL_NAMES:
            continue
        query_attempts += 1
        status = _get(entry, "status")
        arguments = _mapping(_get(entry, "arguments", {}))
        result = _entry_result(entry)
        direction = arguments.get("direction", "path" if tool == "graph_path" else "both")
        if not isinstance(direction, str):
            direction = "unknown"
        mode = "graph_path" if tool == "graph_path" else direction
        query_modes[mode] += 1
        successful = status == "ok" and bool(result)
        if successful:
            query_successes += 1
            evidence_id = _get(entry, "evidence_id")
            truncated = result.get("truncated") is True
            if truncated:
                query_truncated += 1
            complete = result.get("coverage_status") == "complete_for_query" and not truncated
            if complete:
                query_complete += 1
            else:
                query_partial += 1
            relation_types.update(_strings(result.get("observed_relation_types")))
            relation_types.update(_strings(result.get("impact_relation_types")))
            graph_queries.append({
                "ledger_index": index,
                "evidence_id": evidence_id if isinstance(evidence_id, str) else None,
                "tool": tool,
                "mode": mode,
                "complete": complete,
                "truncated": truncated,
                "source_path_count": len(_source_paths(result)),
            })
        else:
            query_failed += 1
            graph_queries.append({
                "ledger_index": index,
                "evidence_id": _get(entry, "evidence_id") if isinstance(_get(entry, "evidence_id"), str) else None,
                "tool": tool,
                "mode": mode,
                "complete": False,
                "truncated": False,
                "source_path_count": 0,
            })

    for index, entry in enumerate(entries):
        tool = _get(entry, "tool")
        if tool not in GRAPH_DERIVED_TOOL_NAMES or _get(entry, "status") != "ok":
            continue
        result = _entry_result(entry)
        if result.get("coverage_status") != "complete_for_query" or result.get("truncated") is True:
            continue
        paths, expected_hashes = _discovery_paths_and_hashes(str(tool), result)
        for path in paths:
            record = surfaced.get(path)
            if record is None:
                surfaced[path] = {
                    "first_query_index": index,
                    "expected_hashes": set(expected_hashes.get(path, set())),
                }
            else:
                record["expected_hashes"].update(expected_hashes.get(path, set()))

    read_entries: list[tuple[int, str, Mapping[str, Any]]] = []
    for index, entry in enumerate(entries):
        if _get(entry, "tool") != "read_source_file" or _get(entry, "status") != "ok":
            continue
        result = _entry_result(entry)
        path = result.get("path")
        if isinstance(path, str) and path:
            read_entries.append((index, path, result))

    already_read_before: set[str] = set()
    already_verified_before: set[str] = set()
    verified_paths: set[str] = set()
    read_after_paths: set[str] = set()
    incomplete_read_paths: set[str] = set()
    hash_mismatch_paths: set[str] = set()
    hash_unavailable_paths: set[str] = set()
    not_followed_paths: set[str] = set()
    for path, record in surfaced.items():
        first_query_index = record["first_query_index"]
        prior_reads = [item for item in read_entries if item[1] == path and item[0] < first_query_index]
        if prior_reads:
            already_read_before.add(path)
        expected_hashes = record["expected_hashes"]
        prior_verified = (
            len(expected_hashes) == 1
            and any(
                _complete_source_read(read_result)
                and read_result.get("source_sha256") == next(iter(expected_hashes))
                for _index, _path, read_result in prior_reads
            )
        )
        if prior_verified:
            already_verified_before.add(path)
            continue
        after_reads = [item for item in read_entries if item[1] == path and item[0] > first_query_index]
        if not after_reads:
            not_followed_paths.add(path)
            continue
        read_after_paths.add(path)
        if len(expected_hashes) != 1:
            hash_unavailable_paths.add(path)
            continue
        expected_hash = next(iter(expected_hashes))
        complete_matching = False
        saw_incomplete = False
        saw_hash_mismatch = False
        for _index, _path, read_result in after_reads:
            if not _complete_source_read(read_result):
                saw_incomplete = True
                continue
            actual_hash = read_result.get("source_sha256")
            if actual_hash == expected_hash:
                complete_matching = True
                break
            if isinstance(actual_hash, str):
                saw_hash_mismatch = True
        if complete_matching:
            verified_paths.add(path)
        elif saw_hash_mismatch:
            hash_mismatch_paths.add(path)
        elif saw_incomplete:
            incomplete_read_paths.add(path)
        else:
            hash_unavailable_paths.add(path)

    eligible_path_count = len(surfaced) - len(already_verified_before)
    followthrough_rate = (
        round(len(verified_paths) / eligible_path_count, 6)
        if eligible_path_count > 0 else None
    )

    claim_assessment = _mapping(claim_evidence_assessment)
    claim_items = claim_assessment.get("items", [])
    if not isinstance(claim_items, list):
        claim_items = []
    claim_count = sum(isinstance(item, Mapping) for item in claim_items)
    claims_with_any_evidence = 0
    claims_with_graph_evidence = 0
    cited_graph_ids: set[str] = set()
    graph_citation_count = 0
    for item in claim_items:
        if not isinstance(item, Mapping):
            continue
        refs = _strings(item.get("evidence_refs"))
        if refs:
            claims_with_any_evidence += 1
        matched = refs & graph_tool_evidence_ids
        if matched:
            claims_with_graph_evidence += 1
            graph_citation_count += len(matched)
            cited_graph_ids.update(matched)

    budget_map = _mapping(budget)
    resource_keys = (
        "model_rounds_used",
        "provider_requests_attempted",
        "provider_reported_tokens",
        "total_prompt_chars",
        "total_evidence_bytes",
        "elapsed_seconds",
        "estimated_cost_usd_reserved",
        "provider_reported_cost_usd",
    )
    resource_usage: dict[str, Any] = {}
    for key in resource_keys:
        value = budget_map.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int) and value >= 0:
            resource_usage[key] = value
        elif isinstance(value, (int, float)) and math.isfinite(float(value)) and value >= 0:
            resource_usage[key] = round(float(value), 8 if "cost" in key else 3)
    if query_attempts and isinstance(resource_usage.get("provider_reported_tokens"), int):
        resource_usage["reported_tokens_per_graph_query"] = round(
            resource_usage["provider_reported_tokens"] / query_attempts, 3
        )
    else:
        resource_usage["reported_tokens_per_graph_query"] = None

    backend = _runtime_backend(runtime_architecture)
    status = (
        "policy_violation_observed" if not graph_derived_tools_enabled and sum(
            value["attempt_count"] for value in usage.values()
        ) > 0
        else "not_available_by_design" if not graph_derived_tools_enabled
        else "no_graph_use_observed" if sum(value["attempt_count"] for value in usage.values()) == 0
        else "observed"
    )

    return {
        "schema_version": "ae32c/graph-utilization-assessment/v1",
        "status": status,
        "graph_tools_enabled": bool(graph_tools_enabled),
        "graph_derived_tools_enabled": bool(graph_derived_tools_enabled),
        "graph_derived_tool_usage": usage,
        "graph_query_usage": {
            "attempt_count": query_attempts,
            "successful_call_count": query_successes,
            "complete_query_count": query_complete,
            "partial_or_truncated_query_count": query_partial,
            "truncated_query_count": query_truncated,
            "failed_call_count": query_failed,
            "mode_counts": dict(sorted(query_modes.items())),
            "observed_relation_types": sorted(relation_types),
            "queries": graph_queries[:100],
            "query_records_truncated": len(graph_queries) > 100,
        },
        "source_follow_through": {
            "graph_surfaced_unique_path_count": len(surfaced),
            "paths_already_read_before_graph_surfacing": sorted(already_read_before)[:100],
            "paths_already_verified_before_graph_surfacing": sorted(already_verified_before)[:100],
            "eligible_newly_surfaced_path_count": eligible_path_count,
            "paths_read_after_graph_surfacing": sorted(read_after_paths)[:100],
            "verified_complete_hash_matching_path_count": len(verified_paths),
            "verified_paths": sorted(verified_paths)[:100],
            "not_followed_path_count": len(not_followed_paths),
            "not_followed_paths": sorted(not_followed_paths)[:100],
            "incomplete_read_path_count": len(incomplete_read_paths),
            "hash_mismatch_path_count": len(hash_mismatch_paths),
            "hash_unavailable_path_count": len(hash_unavailable_paths),
            "verified_follow_through_rate": followthrough_rate,
        },
        "claim_linkage": {
            "claim_count": claim_count,
            "claims_with_any_ledger_evidence_count": claims_with_any_evidence,
            "claims_citing_graph_tool_evidence_count": claims_with_graph_evidence,
            "graph_tool_evidence_citation_count": graph_citation_count,
            "graph_tool_evidence_ids_cited": sorted(cited_graph_ids),
            "graph_tool_evidence_id_count": len(graph_tool_evidence_ids),
            "graph_claim_linkage_rate": (
                round(claims_with_graph_evidence / claim_count, 6) if claim_count else None
            ),
        },
        "backend": backend,
        "provider_resource_usage": resource_usage,
        "interpretation_limits": [
            "Tool invocation proves that a graph-derived operation was requested and recorded, not that the model used its result correctly.",
            "A graph-surfaced source read is counted as verified only when it follows surfacing, is complete for the requested range, and matches the graph snapshot hash.",
            "Claim linkage measures references to graph-tool ledger records; it does not establish semantic entailment or causal correctness.",
            "Token and cost measurements are provider-reported or explicitly labelled estimates.",
            "A single run does not establish graph benefit, accuracy improvement, or causal superiority over a counterfactual.",
        ],
    }


def summarize_graph_utilization_assessment(value: Any) -> dict[str, Any]:
    """Return a compact whitelist-only summary for comparison records."""
    assessment = _mapping(value)
    if assessment.get("schema_version") != "ae32c/graph-utilization-assessment/v1":
        return {"status": "not_available"}
    queries = _mapping(assessment.get("graph_query_usage"))
    follow = _mapping(assessment.get("source_follow_through"))
    claims = _mapping(assessment.get("claim_linkage"))
    backend = _mapping(assessment.get("backend"))
    resources = _mapping(assessment.get("provider_resource_usage"))
    return {
        "status": assessment.get("status", "unknown"),
        "active_computation_backend": backend.get("active_computation_backend"),
        "backend_library_version": backend.get("backend_library_version"),
        "graph_tool_attempt_count": sum(
            int(_mapping(item).get("attempt_count", 0))
            for item in _mapping(assessment.get("graph_derived_tool_usage")).values()
        ),
        "graph_query_attempt_count": queries.get("attempt_count", 0),
        "graph_query_success_count": queries.get("successful_call_count", 0),
        "graph_query_complete_count": queries.get("complete_query_count", 0),
        "graph_query_failed_count": queries.get("failed_call_count", 0),
        "graph_impact_query_count": _mapping(queries.get("mode_counts")).get("impact", 0),
        "graph_dependency_query_count": (
            _mapping(queries.get("mode_counts")).get("dependencies", 0)
            + _mapping(queries.get("mode_counts")).get("dependents", 0)
        ),
        "graph_surfaced_path_count": follow.get("graph_surfaced_unique_path_count", 0),
        "graph_verified_follow_through_path_count": follow.get("verified_complete_hash_matching_path_count", 0),
        "graph_verified_follow_through_rate": follow.get("verified_follow_through_rate"),
        "claims_citing_graph_tool_evidence_count": claims.get("claims_citing_graph_tool_evidence_count", 0),
        "claim_count": claims.get("claim_count", 0),
        "reported_tokens": resources.get("provider_reported_tokens"),
        "reported_cost_usd": resources.get("provider_reported_cost_usd"),
        "elapsed_seconds": resources.get("elapsed_seconds"),
    }


def aggregate_graph_utilization_runs(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate descriptive process metrics without estimating causal graph benefit."""
    normalized = [item for item in runs if isinstance(item, Mapping)]
    metrics = (
        "graph_tool_attempt_count",
        "graph_query_attempt_count",
        "graph_query_success_count",
        "graph_query_complete_count",
        "graph_verified_follow_through_path_count",
        "claims_citing_graph_tool_evidence_count",
        "reported_tokens",
        "elapsed_seconds",
        "baseline_reported_tokens",
        "graph_assisted_reported_tokens",
        "baseline_elapsed_seconds",
        "graph_assisted_elapsed_seconds",
        "graph_assisted_tool_call_count",
    )
    groups: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = {}
    for run in normalized:
        key = (
            str(run.get("provider", "unknown")),
            str(run.get("model", "unknown")),
            str(run.get("active_computation_backend", "unknown")),
            str(run.get("source_manifest_sha256", "unknown")),
        )
        groups.setdefault(key, []).append(run)
    summaries = []
    for key, group in sorted(groups.items()):
        aggregate: dict[str, Any] = {}
        for metric in metrics:
            values = [
                float(item[metric]) for item in group
                if isinstance(item.get(metric), (int, float))
                and not isinstance(item.get(metric), bool)
                and math.isfinite(float(item[metric]))
                and float(item[metric]) >= 0
            ]
            aggregate[metric] = {
                "observed_run_count": len(values),
                "total": round(sum(values), 6) if values else None,
                "mean": round(sum(values) / len(values), 6) if values else None,
            }
        summaries.append({
            "provider": key[0],
            "model": key[1],
            "active_computation_backend": key[2],
            "source_manifest_sha256": key[3],
            "sample_count": len(group),
            "metrics": aggregate,
        })
    return {
        "schema_version": "ae32c/graph-utilization-aggregate/v1",
        "run_count": len(normalized),
        "group_count": len(summaries),
        "groups": summaries,
        "interpretation_limits": [
            "Aggregates are descriptive process telemetry only.",
            "Runs are grouped by provider, model, backend and exact source-manifest hash; different snapshots are not pooled.",
            "No diagnostic accuracy, graph benefit, causal effect, or statistical significance is inferred.",
            "Repeated runs are not counterbalanced unless the experiment design separately establishes that property.",
        ],
    }
