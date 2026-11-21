#!/usr/bin/env python3
"""Deterministic native graph-backend conformance runner for AE-32C E.8.5.

The runner exercises an in-memory semantic multigraph, verifies that the
selected native projection round-trips every node and edge occurrence, and
compares bounded traversal results with the canonical Python reference.
It does not read repository source, call providers, access the network, or
modify repository files.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping
from importlib import metadata as importlib_metadata
from importlib.util import find_spec
import json
import platform
from pathlib import Path
import sys
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from audit_engine.semantic_audit.core.semantic_graph import (  # noqa: E402
    SemanticEdge,
    SemanticGraph,
    SemanticNode,
)
from audit_engine.semantic_audit.graph.analysis.models import TraversalDirection  # noqa: E402
from audit_engine.semantic_audit.graph.analysis.traversal import (  # noqa: E402
    GraphTraversalEngine,
)
from audit_engine.semantic_audit.graph.backend.adapter_traversal import (  # noqa: E402
    NativeAdapterGraphTraversalEngine,
)
from audit_engine.semantic_audit.graph.backend.networkx_traversal import (  # noqa: E402
    NetworkXGraphTraversalEngine,
    _EDGE_OCCURRENCE_KEY,
)
from audit_engine.semantic_audit.graph.backend.optional_backend_support import (  # noqa: E402
    BackendUnavailableError,
    require_backend,
)

BACKENDS = ("networkx", "scipy", "igraph", "graph-tool", "snap")
MODULES = {
    "networkx": "networkx",
    "scipy": "scipy",
    "igraph": "igraph",
    "graph-tool": "graph_tool",
    "snap": "snap",
}
DISTRIBUTIONS = {
    "networkx": "networkx",
    "scipy": "scipy",
    "igraph": "igraph",
    "graph-tool": "graph-tool-base",
    "snap": "snap-stanford",
}
PROJECTION_TYPES = {
    "networkx": "networkx.MultiDiGraph",
    "scipy": "scipy.sparse.csr_matrix+semantic-side-channels",
    "igraph": "igraph.Graph(directed=True)",
    "graph-tool": "graph_tool.Graph(directed=True)",
    "snap": "snap.TNEANet",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    )


def _digest(value: Any) -> str:
    import hashlib
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def probe_backend(backend: str) -> dict[str, Any]:
    """Report discoverability and importability without claiming conformance."""
    if backend not in BACKENDS:
        raise ValueError(f"Unknown backend: {backend}")
    module_name = MODULES[backend]
    try:
        discoverable = find_spec(module_name) is not None
    except (ImportError, ValueError):
        discoverable = False
    if not discoverable:
        return {
            "backend": backend,
            "module": module_name,
            "distribution": DISTRIBUTIONS[backend],
            "status": "not_installed",
            "native_conformance": "not_run",
            "reason": "native_module_not_discoverable",
        }
    try:
        module = require_backend(backend)
    except (ImportError, OSError, AttributeError, ValueError) as exc:
        return {
            "backend": backend,
            "module": module_name,
            "distribution": DISTRIBUTIONS[backend],
            "status": "incompatible",
            "native_conformance": "not_run",
            "reason": f"{type(exc).__name__}:{exc}",
        }
    try:
        version = importlib_metadata.version(DISTRIBUTIONS[backend])
    except importlib_metadata.PackageNotFoundError:
        version = str(getattr(module, "__version__", "unknown"))
    return {
        "backend": backend,
        "module": module_name,
        "distribution": DISTRIBUTIONS[backend],
        "version": version,
        "status": "available",
        "native_conformance": "not_run",
    }


def fixture() -> SemanticGraph:
    """Small but adversarial directed multigraph using JSON-compatible payloads."""
    graph = SemanticGraph()
    nodes = [
        SemanticNode(
            "alpha", "PythonModule",
            {"path": "alpha.py", "labels": ["entry", "λ"], "enabled": True},
            {"source": "e85-fixture", "range": {"start": 1, "end": 20}},
        ),
        SemanticNode(
            "beta", "PythonModule",
            {"path": "beta.py", "score": 0.75, "tags": ["consumer"]},
            {"source": "e85-fixture", "optional": None},
        ),
        SemanticNode(
            "gamma", "PythonSymbol",
            {"name": "run", "arity": 2},
            {"source": "e85-fixture", "line": 17},
        ),
        SemanticNode(
            "delta", "PythonTest",
            {"path": "tests/test_alpha.py", "selected": False},
            {"source": "e85-fixture", "suite": "unit"},
        ),
        SemanticNode(
            "epsilon", "IsolatedEntity",
            {"path": "unused.py"},
            {"source": "e85-fixture", "isolated": True},
        ),
    ]
    for node in nodes:
        graph.add_node(node)

    edges = [
        SemanticEdge(
            "alpha", "beta", "IMPORTS",
            {"ordinal": 1, "flags": ["primary", "direct"]},
            {"path": "alpha.py", "line": 4, "unicode": "λ"},
        ),
        # Same source, target AND relation: this is a true parallel occurrence.
        SemanticEdge(
            "alpha", "beta", "IMPORTS",
            {"ordinal": 2, "flags": ["secondary"]},
            {"path": "alpha.py", "line": 5, "unicode": "雪"},
        ),
        SemanticEdge(
            "alpha", "beta", "DEPENDS_ON",
            {"ordinal": 3, "weight": 1.25},
            {"path": "alpha.py", "line": 6},
        ),
        SemanticEdge(
            "alpha", "delta", "TESTS",
            {"ordinal": 4}, {"path": "alpha.py", "line": 9},
        ),
        SemanticEdge(
            "beta", "gamma", "CALLS",
            {"ordinal": 5}, {"path": "beta.py", "line": 12},
        ),
        SemanticEdge(
            "gamma", "alpha", "CALLS",
            {"ordinal": 6}, {"path": "gamma.py", "line": 19},
        ),
        SemanticEdge(
            "gamma", "gamma", "SELF_LOOP",
            {"ordinal": 7}, {"path": "gamma.py", "line": 20},
        ),
        SemanticEdge(
            "delta", "alpha", "IMPORTS",
            {"ordinal": 8}, {"path": "tests/test_alpha.py", "line": 2},
        ),
    ]
    for edge in edges:
        graph.add_edge(edge)
    return graph


def _expected_nodes(graph: SemanticGraph) -> dict[str, dict[str, Any]]:
    return {
        node.node_id: {
            "id": node.node_id,
            "type": node.entity_type,
            "attributes": node.attributes,
            "metadata": node.metadata,
        }
        for node in graph.nodes
    }


def _expected_edges(graph: SemanticGraph) -> dict[int, dict[str, Any]]:
    return {
        index: {
            "occurrence": index,
            "source": edge.source_id,
            "target": edge.target_id,
            "relation": edge.relation_type,
            "attributes": edge.attributes,
            "metadata": edge.metadata,
        }
        for index, edge in enumerate(graph.edges)
    }


def _native_projection_payloads(backend: str, engine: Any):
    if backend == "networkx":
        native = engine.native_graph
        nodes = []
        for node_id, data in native.nodes(data=True):
            nodes.append({
                "id": node_id,
                "type": data.get("entity_type"),
                "attributes": data.get("attributes"),
                "metadata": data.get("metadata"),
            })
        edges = []
        for source, target, _key, data in native.edges(keys=True, data=True):
            edges.append({
                "occurrence": data.get(_EDGE_OCCURRENCE_KEY),
                "source": source,
                "target": target,
                "relation": data.get("relation"),
                "attributes": data.get("attributes"),
                "metadata": data.get("metadata"),
            })
        return nodes, edges
    return (
        list(engine.adapter.iter_native_nodes()),
        list(engine.adapter.iter_native_edges()),
    )


def _verify_round_trip(backend: str, engine: Any, graph: SemanticGraph) -> dict[str, Any]:
    native_nodes, native_edges = _native_projection_payloads(backend, engine)
    node_map = {item.get("id"): item for item in native_nodes}
    edge_map = {item.get("occurrence"): item for item in native_edges}
    if len(node_map) != len(native_nodes) or len(node_map) != len(graph.nodes):
        raise RuntimeError(f"{backend}: native_node_identity_or_count_mismatch")
    if len(edge_map) != len(native_edges) or len(edge_map) != len(graph.edges):
        raise RuntimeError(f"{backend}: native_edge_occurrence_or_count_mismatch")
    expected_nodes = _expected_nodes(graph)
    expected_edges = _expected_edges(graph)
    if node_map != expected_nodes:
        raise RuntimeError(f"{backend}: native_node_payload_round_trip_mismatch")
    if edge_map != expected_edges:
        raise RuntimeError(f"{backend}: native_edge_payload_round_trip_mismatch")
    return {
        "status": "passed",
        "exact": True,
        "node_count": len(node_map),
        "edge_occurrence_count": len(edge_map),
        "parallel_edge_occurrences": 3,
        "self_loop_occurrences": 1,
        "round_trip_sha256": _digest({
            "nodes": [node_map[key] for key in sorted(node_map)],
            "edges": [edge_map[key] for key in sorted(edge_map)],
        }),
    }


def _scenario_definitions():
    return [
        ("outgoing_all", "alpha", {
            "direction": TraversalDirection.OUTGOING,
            "max_depth": 5,
        }, False, None),
        ("incoming_all", "alpha", {
            "direction": TraversalDirection.INCOMING,
            "max_depth": 5,
        }, False, None),
        ("bidirectional_all", "alpha", {
            "direction": TraversalDirection.BOTH,
            "max_depth": 5,
        }, False, None),
        ("relation_filter", "alpha", {
            "direction": TraversalDirection.OUTGOING,
            "relation_types": ("IMPORTS",),
            "max_depth": 5,
        }, False, None),
        ("depth_bound", "alpha", {
            "direction": TraversalDirection.OUTGOING,
            "max_depth": 1,
        }, False, None),
        ("visited_node_bound", "alpha", {
            "direction": TraversalDirection.OUTGOING,
            "max_depth": 5,
            "max_visited_nodes": 2,
        }, True, "max_visited_nodes"),
        ("step_bound", "alpha", {
            "direction": TraversalDirection.OUTGOING,
            "max_depth": 5,
            "max_steps": 1,
        }, True, "max_traversal_steps"),
    ]


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


def _make_engine(graph: SemanticGraph, backend: str):
    if backend == "networkx":
        return NetworkXGraphTraversalEngine(graph, verify_parity=True)
    return NativeAdapterGraphTraversalEngine(graph, backend, verify_parity=True)


def run(backend: str) -> dict[str, Any]:
    """Run exact native projection and seven-query parity conformance."""
    if backend not in BACKENDS:
        raise ValueError(f"Unknown backend: {backend}")
    availability = probe_backend(backend)
    if availability["status"] != "available":
        raise BackendUnavailableError(
            f"Backend {backend!r} cannot run native conformance: {availability['status']}"
        )

    graph = fixture()
    engine = _make_engine(graph, backend)
    reference = GraphTraversalEngine(graph)
    projection = _verify_round_trip(backend, engine, graph)
    scenarios = []

    for name, start, kwargs, expected_truncated, expected_stop_reason in _scenario_definitions():
        actual = engine.walk(start, **kwargs)
        expected = reference.walk(start, **kwargs)
        if actual != expected:
            raise RuntimeError(f"{backend}: reference_parity_failure:{name}")
        if actual.truncated is not expected_truncated:
            raise RuntimeError(f"{backend}: truncation_semantics_failure:{name}")
        if actual.stop_reason != expected_stop_reason:
            raise RuntimeError(f"{backend}: stop_reason_failure:{name}")
        repeated = engine.walk(start, **kwargs)
        if repeated != actual:
            raise RuntimeError(f"{backend}: nondeterministic_repeat:{name}")
        scenarios.append({
            "name": name,
            "status": "passed",
            "repeat_deterministic": True,
            "reference_parity": True,
            **_result_summary(actual),
        })

    runtime = engine.runtime_report()
    metrics = runtime.get("backend_execution", {})
    expected_query_count = 2 * len(scenarios)
    if metrics.get("parity_verified_queries") != expected_query_count:
        raise RuntimeError(f"{backend}: parity_query_counter_mismatch")
    if metrics.get("parity_failures") != 0 or metrics.get("queries_failed") != 0:
        raise RuntimeError(f"{backend}: runtime_parity_or_query_failure_counter_nonzero")
    if runtime.get("active_computation_backend") != backend:
        raise RuntimeError(f"{backend}: runtime_backend_identity_mismatch")
    if runtime.get("projection_node_count") != len(graph.nodes):
        raise RuntimeError(f"{backend}: runtime_projection_node_count_mismatch")
    if runtime.get("projection_edge_occurrence_count") != len(graph.edges):
        raise RuntimeError(f"{backend}: runtime_projection_edge_count_mismatch")

    return {
        "schema_version": "ae32c/e85-native-backend-conformance/v1",
        "status": "passed",
        "backend": backend,
        "native_library_version": runtime.get("backend_library_version"),
        "projection_type": runtime.get("backend_projection_type"),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "canonical_graph_fingerprint": runtime.get("backend_projection_fingerprint"),
        "projection_round_trip": projection,
        "conformance_cases": scenarios,
        "case_count": len(scenarios),
        "repeated_query_count": expected_query_count,
        "backend_execution": metrics,
        "backend_loss_assessment": runtime.get("backend_loss_assessment"),
        "repository_code_executed": False,
        "provider_calls": 0,
        "network_calls": 0,
        "filesystem_mutations": 0,
    }


def _write_report(path: Path | None, report: dict[str, Any]) -> None:
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
    print(payload, end="")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=BACKENDS, required=True)
    parser.add_argument("--probe-only", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.probe_only:
        report = {
            "schema_version": "ae32c/e85-native-backend-probe/v1",
            "python_version": platform.python_version(),
            "backend": probe_backend(args.backend),
        }
        _write_report(args.output, report)
        return 0
    try:
        report = run(args.backend)
    except Exception as exc:
        report = {
            "schema_version": "ae32c/e85-native-backend-conformance/v1",
            "status": "failed",
            "backend": args.backend,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "python_version": platform.python_version(),
        }
        _write_report(args.output, report)
        return 1
    _write_report(args.output, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
