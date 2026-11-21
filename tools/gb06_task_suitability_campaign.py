#!/usr/bin/env python3
"""AE-32C M7.2: task-suitability workload campaign for graph computation adapters.

The five libraries are computational options, not competitors. This campaign
records per-backend correctness, native-path use, workload fit dimensions and
operational observations. It deliberately emits no ranking or winner.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import json
import math
import os
import platform
import random
import statistics
import sys
from time import perf_counter_ns
from typing import Any

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from audit_engine.semantic_audit.core.semantic_graph import (
    SemanticEdge, SemanticGraph, SemanticNode,
)
from audit_engine.semantic_audit.graph.analysis.identity import graph_fingerprint
from audit_engine.semantic_audit.graph.analysis.models import TraversalDirection
from audit_engine.semantic_audit.graph.analysis.traversal import GraphTraversalEngine
from audit_engine.semantic_audit.graph.backend.adapter_traversal import NativeAdapterGraphTraversalEngine
from audit_engine.semantic_audit.graph.backend.networkx_traversal import NetworkXGraphTraversalEngine
from tools.gb05_native_backend_performance_benchmark import (
    BACKENDS, NATIVE_MODES, BenchmarkError, _canonical, _digest,
    _native_counts, _result_summary, _runtime, _close_engine,
)

SCHEMA = "ae32c/m7-task-suitability-campaign/v1"
GENERATOR = "ae32c_m7_2_seeded_topology_generator/v1"
WORKLOADS = {
    "sparse_dependency": {
        "nodes": 48, "edges": 96, "family": "sparse_directed_dependency",
        "purpose": "bounded dependency and reachability queries",
        "characteristics": ["sparse", "directed", "cycles"],
    },
    "hub_impact": {
        "nodes": 48, "edges": 176, "family": "hub_heavy_impact",
        "purpose": "impact propagation around high-degree entities",
        "characteristics": ["degree_skew", "high_out_degree", "directed"],
    },
    "parallel_evidence": {
        "nodes": 32, "edges": 144, "family": "parallel_evidence_multigraph",
        "purpose": "preservation and traversal of repeated typed evidence links",
        "characteristics": ["parallel_edges", "multiple_relations", "self_loops", "metadata"],
    },
    "disconnected_components": {
        "nodes": 64, "edges": 128, "family": "disconnected_components",
        "purpose": "bounded queries across disconnected audit subgraphs",
        "characteristics": ["disconnected", "small_components"],
    },
    "dense_local_neighborhood": {
        "nodes": 32, "edges": 256, "family": "dense_local_neighborhood",
        "purpose": "queries over dense local relationship neighborhoods",
        "characteristics": ["relatively_dense", "high_local_degree", "directed"],
    },
}
TASK_SCOPE = {
    "task_class": "semantic_graph_bounded_traversal",
    "audit_engine_examples": [
        "dependency_context_retrieval",
        "change_impact_candidate_discovery",
        "claim_to_evidence_path_exploration",
        "relationship_neighborhood_inspection",
    ],
    "not_evaluated": [
        "centrality_and_global_graph_statistics",
        "sparse_linear_algebra_or_numerical_solvers",
        "community_detection",
        "ontology_reasoning",
        "repository_evidence_reconstruction_end_to_end",
    ],
}
AUTHORITY = {
    "backend_auto_selection_permitted": False,
    "performance_winner_established": False,
    "task_suitability_decision_established": False,
    "production_approval": False,
    "scientific_approval_permitted": False,
    "graph_mutation_permitted": False,
}


def _make_graph(workload_id: str, seed: int) -> SemanticGraph:
    if workload_id not in WORKLOADS:
        raise BenchmarkError("unknown_workload_family")
    spec = WORKLOADS[workload_id]
    n, edge_count = spec["nodes"], spec["edges"]
    rng = random.Random(seed)
    ids = [f"{workload_id[:4]}-{i:04d}" for i in range(n)]
    graph = SemanticGraph()
    for i, node_id in enumerate(ids):
        graph.add_node(SemanticNode(
            node_id, "AuditEntity",
            {"ordinal": i, "domain": "finite_element_analysis"},
            {"generator": GENERATOR, "seed": seed},
        ))

    pairs: list[tuple[int, int]] = []
    if workload_id == "sparse_dependency":
        pairs.extend((i, i + 1) for i in range(n - 1))
        while len(pairs) < edge_count:
            a, b = rng.randrange(n - 1), rng.randrange(n)
            if a != b:
                pairs.append((a, b))
    elif workload_id == "hub_impact":
        pairs.extend((0, rng.randrange(1, n)) for _ in range(40))
        while len(pairs) < edge_count:
            a = 0 if rng.random() < 0.55 else rng.randrange(n)
            b = rng.randrange(n)
            if a != b:
                pairs.append((a, b))
    elif workload_id == "parallel_evidence":
        pairs.extend((i % n, (i + 1) % n) for i in range(n))
        while len(pairs) < edge_count:
            if len(pairs) % 4 == 0 and pairs:
                pairs.append(rng.choice(pairs))
            elif len(pairs) % 19 == 0:
                a = rng.randrange(n)
                pairs.append((a, a))
            else:
                a, b = rng.randrange(n), rng.randrange(n)
                pairs.append((a, b))
    elif workload_id == "disconnected_components":
        component_size = 8
        for base in range(0, n, component_size):
            pairs.extend((i, i + 1) for i in range(base, base + component_size - 1))
        while len(pairs) < edge_count:
            base = rng.randrange(n // component_size) * component_size
            a, b = base + rng.randrange(component_size), base + rng.randrange(component_size)
            if a != b:
                pairs.append((a, b))
    else:
        for a in range(n):
            for offset in range(1, 9):
                pairs.append((a, (a + offset) % n))
        while len(pairs) < edge_count:
            pairs.append((rng.randrange(n), rng.randrange(n)))
    pairs = pairs[:edge_count]

    relations = ("DEPENDS_ON", "CITES", "DERIVED_FROM", "SUPPORTS")
    for ordinal, (a, b) in enumerate(pairs):
        relation = relations[ordinal % len(relations)]
        graph.add_edge(SemanticEdge(
            ids[a], ids[b], relation,
            {"occurrence_ordinal": ordinal, "weight": 1 + (ordinal % 5)},
            {"evidence_ref": f"evidence:{seed}:{ordinal}", "seed": seed},
        ))
    return graph


def _queries(graph: SemanticGraph) -> tuple:
    ids = [node.node_id for node in graph.nodes]
    return (
        ("outgoing_neighborhood", ids[0], {"direction": TraversalDirection.OUTGOING, "max_depth": 3}),
        ("incoming_neighborhood", ids[len(ids) // 2], {"direction": TraversalDirection.INCOMING, "max_depth": 3}),
        ("bidirectional_neighborhood", ids[0], {"direction": TraversalDirection.BOTH, "max_depth": 2}),
        ("relation_filtered", ids[0], {"direction": TraversalDirection.OUTGOING, "relation_types": ("DEPENDS_ON",), "max_depth": 4}),
        ("bounded_impact", ids[0], {"direction": TraversalDirection.OUTGOING, "max_depth": 5, "max_visited_nodes": 12}),
    )


def _engine(graph: SemanticGraph, backend: str, parity: bool):
    if backend == "networkx":
        return NetworkXGraphTraversalEngine(graph, verify_parity=parity)
    return NativeAdapterGraphTraversalEngine(graph, backend, verify_parity=parity)


def _timing(observations: list[int]) -> dict:
    if len(observations) < 3 or any(type(x) is not int or x < 0 for x in observations):
        raise BenchmarkError("invalid_timing_samples")
    ordered = sorted(observations)
    median = statistics.median(ordered)
    return {
        "unit": "ns", "observations_ns": observations,
        "median_ns": median,
        "p95_ns": ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)],
        "minimum_ns": ordered[0], "maximum_ns": ordered[-1],
        "mad_ns": statistics.median([abs(x - median) for x in ordered]),
    }


def _one_case(backend: str, workload_id: str, seed: int, repeats: int, warmup: int) -> dict:
    graph = _make_graph(workload_id, seed)
    specs = _queries(graph)
    reference = GraphTraversalEngine(graph)
    expected = {
        name: _digest(_result_summary(reference.walk(start, **kwargs)))
        for name, start, kwargs in specs
    }

    preflight = _engine(graph, backend, True)
    try:
        for name, start, kwargs in specs:
            if _digest(_result_summary(preflight.walk(start, **kwargs))) != expected[name]:
                raise BenchmarkError(f"preflight_reference_parity_failure:{workload_id}:{seed}:{name}")
        preflight_runtime = _runtime(preflight)
        preflight_metrics = preflight_runtime.get("backend_execution", {})
        if preflight_runtime.get("backend_native_query_mode") != NATIVE_MODES[backend]:
            raise BenchmarkError("preflight_native_query_mode_mismatch")
        if preflight_metrics.get("parity_failures", 0) != 0:
            raise BenchmarkError("preflight_parity_failure")
    finally:
        _close_engine(preflight)

    started = perf_counter_ns()
    measured = _engine(graph, backend, False)
    construction_ns = max(0, perf_counter_ns() - started)
    try:
        runtime = _runtime(measured)
        if runtime.get("backend_native_query_mode") != NATIVE_MODES[backend]:
            raise BenchmarkError("measured_native_query_mode_mismatch")
        query_reports = []
        for name, start, kwargs in specs:
            check = measured.walk(start, **kwargs)
            if _digest(_result_summary(check)) != expected[name]:
                raise BenchmarkError(f"pre_timing_result_mismatch:{name}")
            for _ in range(warmup):
                result = measured.walk(start, **kwargs)
                if _digest(_result_summary(result)) != expected[name]:
                    raise BenchmarkError(f"warmup_result_mismatch:{name}")
            before = _native_counts(_runtime(measured))
            observations = []
            for _ in range(repeats):
                t0 = perf_counter_ns()
                result = measured.walk(start, **kwargs)
                observations.append(max(0, perf_counter_ns() - t0))
                if _digest(_result_summary(result)) != expected[name]:
                    raise BenchmarkError(f"timed_result_mismatch:{name}")
            after = _native_counts(_runtime(measured))
            delta = {key: after[key] - before[key] for key in before}
            if delta["native_adjacency_lookups"] < repeats:
                raise BenchmarkError(f"native_adjacency_not_observed:{name}")
            query_reports.append({
                "query_id": name, "result_sha256": expected[name],
                "warmup_calls": warmup, "measured_calls": repeats,
                "timing": _timing(observations), "native_metrics_delta": delta,
            })
        final_runtime = _runtime(measured)
        return {
            "workload": {
                "id": workload_id, "family": WORKLOADS[workload_id]["family"],
                "purpose": WORKLOADS[workload_id]["purpose"],
                "characteristics": list(WORKLOADS[workload_id]["characteristics"]),
                "generator": GENERATOR, "seed": seed,
                "nodes": len(graph.nodes), "edge_occurrences": len(graph.edges),
                "graph_sha256": _digest(graph.to_dict()),
                "graph_fingerprint": graph_fingerprint(graph),
                "query_ids": [item[0] for item in specs],
            },
            "measurements": {
                "engine_construction_ns": construction_ns,
                "queries": query_reports,
            },
            "native_execution": {
                "native_query_mode": runtime.get("backend_native_query_mode"),
                "preflight_parity_queries": len(specs),
                "preflight_parity_failures": 0,
                "native_counts": _native_counts(final_runtime),
            },
            "environment": {
                "python": platform.python_version(), "platform": platform.platform(),
                "machine": platform.machine(),
                "backend_library": final_runtime.get("backend_library"),
                "backend_library_version": final_runtime.get("backend_library_version"),
                "projection_type": final_runtime.get("backend_projection_type"),
                "worker": final_runtime.get("backend_worker_info"),
            },
        }
    finally:
        _close_engine(measured)


def make_report(backend: str, *, seeds: list[int], repeats: int = 3,
                warmup: int = 1, workload_ids: list[str] | None = None) -> dict:
    if backend not in BACKENDS:
        raise BenchmarkError("unknown_backend")
    if not isinstance(seeds, list) or not 2 <= len(seeds) <= 5 or any(
        type(s) is not int or not 0 <= s <= 2**32 - 1 for s in seeds
    ) or seeds != sorted(set(seeds)):
        raise BenchmarkError("seeds_must_be_2_to_5_distinct_ascending_integers")
    if type(repeats) is not int or not 3 <= repeats <= 15:
        raise BenchmarkError("repeats_out_of_bounds")
    if type(warmup) is not int or not 0 <= warmup <= 5:
        raise BenchmarkError("warmup_out_of_bounds")
    selected = list(WORKLOADS) if workload_ids is None else workload_ids
    if not selected or len(selected) != len(set(selected)) or any(x not in WORKLOADS for x in selected):
        raise BenchmarkError("invalid_workload_selection")

    cases = [
        _one_case(backend, workload_id, seed, repeats, warmup)
        for workload_id in selected for seed in seeds
    ]
    report = {
        "schema_version": SCHEMA, "status": "passed", "backend": backend,
        "native_query_mode": NATIVE_MODES[backend],
        "task_scope": deepcopy(TASK_SCOPE),
        "configuration": {
            "seeds": list(seeds), "repeats": repeats, "warmup": warmup,
            "workload_ids": selected, "case_count": len(cases),
        },
        "cases": cases,
        "environment": {
            "python": platform.python_version(), "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "provenance": {
            "source_revision": os.environ.get("AE32C_SOURCE_REVISION"),
            "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
            "workflow_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "workflow_name": os.environ.get("GITHUB_WORKFLOW"),
        },
        "authority": dict(AUTHORITY),
        "interpretation": (
            "Per-backend task-suitability observations for bounded semantic traversal. "
            "Libraries are computational options, not competitors. Timings are descriptive "
            "within the recorded environment; no ranking, winner, task-selection decision, "
            "or production approval is established."
        ),
    }
    report["report_sha256"] = _digest(report)
    return report


def verify_report(report: dict) -> dict:
    if not isinstance(report, dict) or report.get("schema_version") != SCHEMA:
        raise BenchmarkError("unknown_report_schema")
    payload = dict(report)
    submitted = payload.pop("report_sha256", None)
    if submitted != _digest(payload):
        raise BenchmarkError("report_digest_mismatch")
    backend = payload.get("backend")
    if backend not in BACKENDS or payload.get("status") != "passed":
        raise BenchmarkError("backend_or_status_invalid")
    if payload.get("native_query_mode") != NATIVE_MODES[backend]:
        raise BenchmarkError("native_query_mode_invalid")
    if payload.get("task_scope") != TASK_SCOPE or payload.get("authority") != AUTHORITY:
        raise BenchmarkError("task_scope_or_authority_boundary_invalid")
    if any(key in payload for key in ("recommended_backend", "performance_winner", "task_suitability_decision")):
        raise BenchmarkError("report_must_not_select_backend_or_task_winner")
    config = payload.get("configuration", {})
    seeds, workload_ids = config.get("seeds"), config.get("workload_ids")
    if not isinstance(seeds, list) or not 2 <= len(seeds) <= 5 or any(type(x) is not int or not 0 <= x <= 2**32 - 1 for x in seeds) or seeds != sorted(set(seeds)):
        raise BenchmarkError("configuration_seed_set_invalid")
    if type(config.get("repeats")) is not int or not 3 <= config["repeats"] <= 15:
        raise BenchmarkError("configuration_repeat_count_invalid")
    if type(config.get("warmup")) is not int or not 0 <= config["warmup"] <= 5:
        raise BenchmarkError("configuration_warmup_invalid")
    if not isinstance(workload_ids, list) or not workload_ids or len(workload_ids) != len(set(workload_ids)) or any(x not in WORKLOADS for x in workload_ids):
        raise BenchmarkError("configuration_workload_set_invalid")
    cases = payload.get("cases")
    expected_keys = [(wid, seed) for wid in workload_ids for seed in seeds]
    if not isinstance(cases, list) or len(cases) != len(expected_keys) or config.get("case_count") != len(cases):
        raise BenchmarkError("case_count_invalid")

    for case, (workload_id, seed) in zip(cases, expected_keys):
        graph = _make_graph(workload_id, seed)
        manifest = case.get("workload", {})
        if (
            manifest.get("id") != workload_id or manifest.get("seed") != seed
            or manifest.get("family") != WORKLOADS[workload_id]["family"]
            or manifest.get("purpose") != WORKLOADS[workload_id]["purpose"]
            or manifest.get("characteristics") != WORKLOADS[workload_id]["characteristics"]
            or manifest.get("generator") != GENERATOR
            or manifest.get("nodes") != len(graph.nodes)
            or manifest.get("edge_occurrences") != len(graph.edges)
            or manifest.get("graph_sha256") != _digest(graph.to_dict())
            or manifest.get("graph_fingerprint") != graph_fingerprint(graph)
        ):
            raise BenchmarkError(f"workload_reconstruction_mismatch:{workload_id}:{seed}")
        if manifest.get("query_ids") != [x[0] for x in _queries(graph)]:
            raise BenchmarkError("query_manifest_mismatch")
        if case.get("native_execution", {}).get("native_query_mode") != NATIVE_MODES[backend]:
            raise BenchmarkError("case_native_mode_mismatch")
        if case.get("native_execution", {}).get("preflight_parity_failures") != 0:
            raise BenchmarkError("case_parity_failure")
        if case.get("native_execution", {}).get("preflight_parity_queries") != len(_queries(graph)):
            raise BenchmarkError("case_parity_query_count_invalid")
        case_env = case.get("environment", {})
        report_env = payload.get("environment", {})
        if any(case_env.get(key) != report_env.get(key) for key in ("python", "platform", "machine")):
            raise BenchmarkError("mixed_environment_within_backend_report")
        queries = case.get("measurements", {}).get("queries")
        specs = _queries(graph)
        if not isinstance(queries, list) or [q.get("query_id") for q in queries] != [x[0] for x in specs]:
            raise BenchmarkError("query_records_invalid")
        reference = GraphTraversalEngine(graph)
        for item, (name, start, kwargs) in zip(queries, specs):
            expected = _digest(_result_summary(reference.walk(start, **kwargs)))
            if item.get("result_sha256") != expected:
                raise BenchmarkError(f"reference_result_digest_mismatch:{name}")
            if item.get("warmup_calls") != config["warmup"] or item.get("measured_calls") != config["repeats"]:
                raise BenchmarkError("sample_configuration_mismatch")
            timing = item.get("timing", {})
            observations = timing.get("observations_ns")
            if not isinstance(observations, list) or len(observations) != config["repeats"]:
                raise BenchmarkError("timing_sample_count_mismatch")
            recomputed = _timing(observations)
            for key in ("median_ns", "p95_ns", "minimum_ns", "maximum_ns", "mad_ns"):
                if timing.get(key) != recomputed[key]:
                    raise BenchmarkError(f"timing_aggregate_mismatch:{name}:{key}")
            native = item.get("native_metrics_delta", {})
            if native.get("native_adjacency_lookups", 0) < config["repeats"]:
                raise BenchmarkError("native_lookup_count_invalid")
    return {
        "status": "verified", "backend": backend,
        "case_count": len(cases),
        "workload_families": workload_ids,
        "seed_count": len(seeds), "query_records": sum(len(x["measurements"]["queries"]) for x in cases),
        "report_sha256": submitted,
        "performance_winner_established": False,
        "task_suitability_decision_established": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--backend", choices=BACKENDS, required=True)
    run.add_argument("--seeds", default="20261101,20261102")
    run.add_argument("--repeats", type=int, default=3)
    run.add_argument("--warmup", type=int, default=1)
    run.add_argument("--workloads", default=",".join(WORKLOADS))
    run.add_argument("--report", required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    try:
        from pathlib import Path
        path = Path(args.report)
        if args.command == "run":
            seeds = [int(x) for x in args.seeds.split(",") if x.strip()]
            workload_ids = [x.strip() for x in args.workloads.split(",") if x.strip()]
            report = make_report(args.backend, seeds=seeds, repeats=args.repeats,
                                 warmup=args.warmup, workload_ids=workload_ids)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                       sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        else:
            report = json.loads(path.read_text(encoding="utf-8"))
        print(json.dumps(verify_report(report), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__,
                          "error": str(exc)}, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
