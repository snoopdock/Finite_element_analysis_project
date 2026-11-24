#!/usr/bin/env python3
"""AE-32C M7.1: parity-gated smoke benchmark for all five native backends.

This first harness intentionally uses the fixed adversarial E.8.5 fixture.
It measures engine construction and warm traversal calls separately, records
native adjacency telemetry, and replays expected results through the canonical
Python reference. It is a scaffold, not a comparative performance campaign.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
import platform
import statistics
import sys
from time import perf_counter_ns
from typing import Any

REPOSITORY_ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph
from audit_engine.semantic_audit.graph.analysis.identity import graph_fingerprint
from audit_engine.semantic_audit.graph.analysis.models import TraversalDirection
from audit_engine.semantic_audit.graph.analysis.traversal import GraphTraversalEngine
from audit_engine.semantic_audit.graph.backend.adapter_traversal import (
    NativeAdapterGraphTraversalEngine,
)
from audit_engine.semantic_audit.graph.backend.networkx_traversal import (
    NetworkXGraphTraversalEngine,
)
from tools.gb03_native_backend_conformance import fixture

SCHEMA = "ae32c/m7-native-backend-benchmark/v1"
BACKENDS = ("networkx", "scipy", "igraph", "graph-tool", "snap")
NATIVE_MODES = {
    "networkx": "networkx_successor_predecessor_adjacency",
    "scipy": "scipy_csr_csc_adjacency",
    "igraph": "igraph_incident_edge_ids",
    "graph-tool": "graph_tool_vertex_edge_iterators",
    "snap": "snap_isolated_worker_tneanet_edge_ids",
}
AUTHORITY = {
    "backend_auto_selection_permitted": False,
    "performance_winner_established": False,
    "production_approval": False,
    "scientific_approval_permitted": False,
    "graph_mutation_permitted": False,
}


class BenchmarkError(ValueError):
    """Invalid benchmark configuration, parity, telemetry or report."""


def _canonical(value: Any) -> bytes:
    return (json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return sha256(_canonical(value)).hexdigest()


def _queries():
    return (
        ("outgoing_all", "alpha", {
            "direction": TraversalDirection.OUTGOING, "max_depth": 5,
        }),
        ("incoming_all", "alpha", {
            "direction": TraversalDirection.INCOMING, "max_depth": 5,
        }),
        ("bidirectional_all", "alpha", {
            "direction": TraversalDirection.BOTH, "max_depth": 5,
        }),
        ("relation_filter", "alpha", {
            "direction": TraversalDirection.OUTGOING,
            "relation_types": ("IMPORTS",), "max_depth": 5,
        }),
        ("depth_bound", "alpha", {
            "direction": TraversalDirection.OUTGOING, "max_depth": 1,
        }),
        ("visited_node_bound", "alpha", {
            "direction": TraversalDirection.OUTGOING, "max_depth": 5,
            "max_visited_nodes": 2,
        }),
        ("step_bound", "alpha", {
            "direction": TraversalDirection.OUTGOING, "max_depth": 5,
            "max_steps": 1,
        }),
    )


def _make_engine(graph: SemanticGraph, backend: str, *, verify_parity: bool):
    if backend == "networkx":
        return NetworkXGraphTraversalEngine(graph, verify_parity=verify_parity)
    return NativeAdapterGraphTraversalEngine(
        graph, backend, verify_parity=verify_parity,
    )


def _close_engine(engine) -> None:
    adapter = getattr(engine, "adapter", None)
    close = getattr(adapter, "close", None)
    if callable(close):
        close()


def _install_integrity_timer(engine, backend: str) -> list[int]:
    """Time complete native-projection audits without changing production code.

    The wrapper is installed only on this benchmark instance and after engine
    construction. Constructor audit cost therefore remains inside the existing
    engine_construction_ns measurement.
    """
    observations: list[int] = []
    method_name = "_verify_projection" if backend == "networkx" else "_build_adjacency"
    original = getattr(engine, method_name)

    def timed_audit(*args, **kwargs):
        started = perf_counter_ns()
        try:
            return original(*args, **kwargs)
        finally:
            observations.append(max(0, perf_counter_ns() - started))

    setattr(engine, method_name, timed_audit)
    return observations


def _result_summary(result) -> dict[str, Any]:
    return {
        "visited_nodes": list(result.visited_nodes),
        "step_count": len(result.steps),
        "evidence_count": len(result.evidence),
        "examined_edges": result.examined_edges,
        "truncated": result.truncated,
        "stop_reason": result.stop_reason,
        "graph_fingerprint": result.graph_fingerprint,
    }


def _runtime(engine) -> dict[str, Any]:
    report = engine.runtime_report()
    metrics = report.get("backend_execution")
    if not isinstance(metrics, dict):
        raise BenchmarkError("backend_runtime_metrics_missing")
    return report


def _native_counts(runtime: dict[str, Any]) -> dict[str, int]:
    metrics = runtime.get("backend_execution", {})
    return {
        "native_adjacency_lookups": int(metrics.get("native_adjacency_lookups", 0)),
        "native_edge_occurrences_read": int(metrics.get("native_edge_occurrences_read", 0)),
    }


def _timing_summary(observations: list[int]) -> dict[str, Any]:
    if len(observations) < 3 or any(type(item) is not int or item < 0 for item in observations):
        raise BenchmarkError("timing_observation_set_invalid")
    ordered = sorted(observations)
    return {
        "unit": "ns",
        "observations_ns": observations,
        "median_ns": statistics.median(ordered),
        "p95_ns": ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)],
        "minimum_ns": ordered[0],
        "maximum_ns": ordered[-1],
        "mad_ns": statistics.median(
            [abs(item - statistics.median(ordered)) for item in ordered]
        ),
    }


def make_report(
    backend: str, *, repeats: int = 5, warmup: int = 2,
) -> dict[str, Any]:
    if backend not in BACKENDS:
        raise BenchmarkError("unknown_backend")
    if type(repeats) is not int or not 3 <= repeats <= 15:
        raise BenchmarkError("repeats_out_of_bounds")
    if type(warmup) is not int or not 0 <= warmup <= 5:
        raise BenchmarkError("warmup_out_of_bounds")

    graph = fixture()
    graph_id = graph_fingerprint(graph)
    query_specs = _queries()

    # Correctness is established before the timed engine is created.
    parity_engine = _make_engine(graph, backend, verify_parity=True)
    expected = {}
    try:
        for name, start, kwargs in query_specs:
            result = parity_engine.walk(start, **kwargs)
            expected[name] = _digest(_result_summary(result))
        parity_runtime = _runtime(parity_engine)
        parity_metrics = parity_runtime.get("backend_execution", {})
        if parity_metrics.get("parity_failures", 0) != 0:
            raise BenchmarkError("pre_timing_reference_parity_failure")
        if parity_metrics.get("parity_verified_queries", 0) != len(query_specs):
            raise BenchmarkError("pre_timing_parity_query_count_mismatch")
        if parity_runtime.get("backend_native_query_mode") != NATIVE_MODES[backend]:
            raise BenchmarkError("pre_timing_native_query_mode_mismatch")
    finally:
        _close_engine(parity_engine)

    # Disable the duplicate reference walk only in the timed engine. The
    # exact same seven outputs were already checked above; each timed engine
    # output is also compared with those independently accepted digests.
    started = perf_counter_ns()
    measured_engine = _make_engine(graph, backend, verify_parity=False)
    construction_ns = max(0, perf_counter_ns() - started)
    query_reports = []
    try:
        runtime = _runtime(measured_engine)
        integrity_observations = _install_integrity_timer(measured_engine, backend)
        if runtime.get("backend_native_query_mode") != NATIVE_MODES[backend]:
            raise BenchmarkError("measured_native_query_mode_mismatch")

        for name, start, kwargs in query_specs:
            check = measured_engine.walk(start, **kwargs)
            if _digest(_result_summary(check)) != expected[name]:
                raise BenchmarkError(f"measured_result_parity_mismatch:{name}")

            for _ in range(warmup):
                warm = measured_engine.walk(start, **kwargs)
                if _digest(_result_summary(warm)) != expected[name]:
                    raise BenchmarkError(f"warmup_result_parity_mismatch:{name}")

            before = _native_counts(_runtime(measured_engine))
            integrity_start = len(integrity_observations)
            observations = []
            for _ in range(repeats):
                t0 = perf_counter_ns()
                result = measured_engine.walk(start, **kwargs)
                observations.append(max(0, perf_counter_ns() - t0))
                if _digest(_result_summary(result)) != expected[name]:
                    raise BenchmarkError(f"timed_result_parity_mismatch:{name}")
            after = _native_counts(_runtime(measured_engine))
            audit_observations = integrity_observations[integrity_start:]
            expected_audits = 2 * repeats
            if len(audit_observations) != expected_audits:
                raise BenchmarkError(
                    f"integrity_audit_count_mismatch:{name}:"
                    f"expected={expected_audits}:observed={len(audit_observations)}"
                )
            per_query_integrity_ns = [
                audit_observations[index] + audit_observations[index + 1]
                for index in range(0, len(audit_observations), 2)
            ]
            delta = {
                key: after[key] - before[key] for key in before
            }
            if delta["native_adjacency_lookups"] < repeats:
                raise BenchmarkError(f"native_adjacency_not_observed:{name}")
            if delta["native_edge_occurrences_read"] < 1:
                raise BenchmarkError(f"native_edge_occurrence_reads_missing:{name}")

            query_reports.append({
                "query_id": name,
                "result_sha256": expected[name],
                "warmup_calls": warmup,
                "measured_calls": repeats,
                "timing": _timing_summary(observations),
                "integrity_audit_count": len(audit_observations),
                "integrity_audit_timing": _timing_summary(audit_observations),
                "per_query_integrity_total_timing": _timing_summary(per_query_integrity_ns),
                "native_metrics_delta": delta,
            })

        final_runtime = _runtime(measured_engine)
        worker = final_runtime.get("backend_worker_info")
        report = {
            "schema_version": SCHEMA,
            "status": "passed",
            "backend": backend,
            "native_query_mode": NATIVE_MODES[backend],
            "workload": {
                "id": "e85_adversarial_fixture_v1",
                "graph_fingerprint": graph_id,
                "nodes": len(graph.nodes),
                "edge_occurrences": len(graph.edges),
                "query_count": len(query_specs),
                "query_ids": [item[0] for item in query_specs],
            },
            "configuration": {"repeats": repeats, "warmup": warmup},
            "measurements": {
                "engine_construction_ns": construction_ns,
                "queries": query_reports,
            },
            "native_execution": {
                "parity_preflight_queries": parity_metrics.get("parity_verified_queries", 0),
                "parity_failures": parity_metrics.get("parity_failures", 0),
                "timed_engine_native_counts": _native_counts(final_runtime),
            },
            "environment": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "machine": platform.machine(),
                "backend_library": final_runtime.get("backend_library"),
                "backend_library_version": final_runtime.get("backend_library_version"),
                "projection_type": final_runtime.get("backend_projection_type"),
                "worker": worker,
            },
            "provenance": {
                "source_revision": __import__("os").environ.get("AE32C_SOURCE_REVISION"),
                "workflow_run_id": __import__("os").environ.get("GITHUB_RUN_ID"),
                "workflow_run_attempt": __import__("os").environ.get("GITHUB_RUN_ATTEMPT"),
                "workflow_name": __import__("os").environ.get("GITHUB_WORKFLOW"),
            },
            "authority": dict(AUTHORITY),
            "interpretation": (
                "Single-backend smoke measurements on one fixed fixture. "
                "Not a cross-backend ranking, multi-seed campaign, memory study "
                "or production approval."
            ),
        }
    finally:
        _close_engine(measured_engine)

    report["report_sha256"] = _digest(report)
    return report


def verify_report(report: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(report, dict) or report.get("schema_version") != SCHEMA:
        raise BenchmarkError("unknown_report_schema")
    payload = dict(report)
    submitted = payload.pop("report_sha256", None)
    if submitted != _digest(payload):
        raise BenchmarkError("report_digest_mismatch")
    backend = payload.get("backend")
    if backend not in BACKENDS or payload.get("status") != "passed":
        raise BenchmarkError("report_backend_or_status_invalid")
    if payload.get("native_query_mode") != NATIVE_MODES[backend]:
        raise BenchmarkError("report_native_mode_invalid")
    if payload.get("authority") != AUTHORITY:
        raise BenchmarkError("report_authority_boundary_invalid")
    if "recommended_backend" in payload or "performance_winner" in payload:
        raise BenchmarkError("benchmark_must_not_select_a_winner")

    graph = fixture()
    workload = payload.get("workload", {})
    if (
        workload.get("id") != "e85_adversarial_fixture_v1"
        or workload.get("graph_fingerprint") != graph_fingerprint(graph)
        or workload.get("nodes") != len(graph.nodes)
        or workload.get("edge_occurrences") != len(graph.edges)
    ):
        raise BenchmarkError("workload_source_reconstruction_mismatch")

    queries = payload.get("measurements", {}).get("queries")
    specs = _queries()
    if not isinstance(queries, list) or [item.get("query_id") for item in queries] != [x[0] for x in specs]:
        raise BenchmarkError("query_manifest_mismatch")
    reference = GraphTraversalEngine(graph)
    for item, (name, start, kwargs) in zip(queries, specs):
        expected = _digest(_result_summary(reference.walk(start, **kwargs)))
        if item.get("result_sha256") != expected:
            raise BenchmarkError(f"reference_result_digest_mismatch:{name}")
        timing = item.get("timing", {})
        observations = timing.get("observations_ns")
        if not isinstance(observations, list) or len(observations) != payload.get("configuration", {}).get("repeats"):
            raise BenchmarkError(f"timing_sample_count_mismatch:{name}")
        recomputed = _timing_summary(observations)
        for key in ("median_ns", "p95_ns", "minimum_ns", "maximum_ns", "mad_ns"):
            if timing.get(key) != recomputed[key]:
                raise BenchmarkError(f"timing_aggregate_mismatch:{name}:{key}")
        audit_count = item.get("integrity_audit_count")
        expected_audits = 2 * len(observations)
        if audit_count != expected_audits:
            raise BenchmarkError(f"integrity_audit_count_invalid:{name}")
        audit_timing = item.get("integrity_audit_timing", {})
        audit_observations = audit_timing.get("observations_ns")
        if not isinstance(audit_observations, list) or len(audit_observations) != expected_audits:
            raise BenchmarkError(f"integrity_audit_timing_sample_count_mismatch:{name}")
        audit_recomputed = _timing_summary(audit_observations)
        for key in ("median_ns", "p95_ns", "minimum_ns", "maximum_ns", "mad_ns"):
            if audit_timing.get(key) != audit_recomputed[key]:
                raise BenchmarkError(f"integrity_audit_timing_aggregate_mismatch:{name}:{key}")
        per_query_integrity = item.get("per_query_integrity_total_timing", {})
        per_query_observations = per_query_integrity.get("observations_ns")
        expected_per_query = [
            audit_observations[index] + audit_observations[index + 1]
            for index in range(0, expected_audits, 2)
        ]
        if per_query_observations != expected_per_query:
            raise BenchmarkError(f"per_query_integrity_observations_invalid:{name}")
        per_query_recomputed = _timing_summary(expected_per_query)
        for key in ("median_ns", "p95_ns", "minimum_ns", "maximum_ns", "mad_ns"):
            if per_query_integrity.get(key) != per_query_recomputed[key]:
                raise BenchmarkError(f"per_query_integrity_aggregate_mismatch:{name}:{key}")
        native = item.get("native_metrics_delta", {})
        if native.get("native_adjacency_lookups", 0) < len(observations):
            raise BenchmarkError(f"native_lookup_count_invalid:{name}")
        if native.get("native_edge_occurrences_read", 0) < 1:
            raise BenchmarkError(f"native_occurrence_count_invalid:{name}")

    return {
        "status": "verified",
        "backend": backend,
        "query_count": len(queries),
        "report_sha256": submitted,
        "winner_established": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--backend", choices=BACKENDS, required=True)
    run_parser.add_argument("--repeats", type=int, default=5)
    run_parser.add_argument("--warmup", type=int, default=2)
    run_parser.add_argument("--report", required=True)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)

    try:
        if args.command == "run":
            report = make_report(args.backend, repeats=args.repeats, warmup=args.warmup)
            path = __import__("pathlib").Path(args.report)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
                encoding="utf-8",
            )
            print(json.dumps(verify_report(report), sort_keys=True))
        else:
            path = __import__("pathlib").Path(args.report)
            report = json.loads(path.read_text(encoding="utf-8"))
            print(json.dumps(verify_report(report), sort_keys=True))
    except Exception as exc:
        print(json.dumps({
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
