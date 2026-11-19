#!/usr/bin/env python3
"""Native smoke test for every registered AE-32B graph traversal backend.

Run this in the interpreter/environment that owns the optional native library.
It constructs a small in-memory SemanticGraph, performs a bounded query, and
requires exact per-query parity with the pure-Python reference traversal.
No repository code, provider API, network call, or filesystem mutation occurs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.graph.service import SemanticGraphAnalysisService


BACKENDS = ("networkx", "scipy", "igraph", "graph-tool", "snap")


def fixture() -> SemanticGraph:
    graph = SemanticGraph()
    for node_id in ("alpha", "beta", "gamma"):
        graph.add_node(SemanticNode(
            node_id, "Concept",
            {"unicode": "λ", "label": node_id},
            {"source": "e83-native-smoke"},
        ))
    graph.add_edge(SemanticEdge("alpha", "beta", "IMPORTS", {"ordinal": 1}, {"line": 4}))
    graph.add_edge(SemanticEdge("alpha", "beta", "DEPENDS_ON", {"ordinal": 2}, {"line": 5}))
    graph.add_edge(SemanticEdge("beta", "gamma", "IMPORTS", {"ordinal": 3}, {"line": 8}))
    graph.add_edge(SemanticEdge("gamma", "gamma", "SELF_LOOP", {"ordinal": 4}, {"line": 9}))
    return graph


def run(backend: str) -> dict:
    graph = fixture()
    service = SemanticGraphAnalysisService(
        graph, traversal_backend=backend, verify_backend_parity=True,
    )
    query = GraphQuery(
        f"e83-native-smoke-{backend}",
        QueryType.DEPENDENCY,
        ["alpha"],
        {
            "direction": "outgoing",
            "relation_types": ["IMPORTS", "DEPENDS_ON"],
            "max_depth": 3,
        },
    )
    result = service.analyze(query)
    runtime = service.engine.traversal_engine.runtime_report()
    if result.discovered_entities != ("beta", "gamma"):
        raise RuntimeError(f"{backend}: unexpected discovered entities")
    if runtime.get("backend_execution", {}).get("parity_verified_queries") != 1:
        raise RuntimeError(f"{backend}: reference parity was not verified")
    if runtime.get("active_computation_backend") != backend:
        raise RuntimeError(f"{backend}: selected backend identity mismatch")
    return {
        "schema_version": "ae32c/e83-native-backend-smoke/v1",
        "backend": backend,
        "status": "passed",
        "native_library_version": runtime.get("backend_library_version"),
        "projection_type": runtime.get("backend_projection_type"),
        "node_count": len(graph.nodes),
        "edge_occurrence_count": len(graph.edges),
        "discovered_entities": list(result.discovered_entities),
        "parity_status": result.metadata.get("backend_parity_status"),
        "backend_loss_assessment": runtime.get("backend_loss_assessment"),
        "backend_execution": runtime.get("backend_execution"),
        "repository_code_executed": False,
        "network_calls_performed": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=BACKENDS, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = run(args.backend)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
