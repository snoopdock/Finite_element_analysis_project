"""M7.4-G4 cross-backend snapshot and mutation-integrity tests.

These tests target the canonical-graph authority boundary. They do not claim
that synthetic fixtures qualify repository-file side effects or all concurrent
mutation schedules; those remain separately identified limits in the G4 record.
"""
from __future__ import annotations

import copy
import os
from dataclasses import replace
from importlib.util import find_spec

import pytest

from audit_engine.semantic_audit.core.semantic_graph import (
    SemanticEdge,
    SemanticGraph,
    SemanticNode,
)
from audit_engine.semantic_audit.graph.analysis import TraversalDirection
from audit_engine.semantic_audit.graph.backend.adapter_traversal import (
    NativeAdapterGraphTraversalEngine,
)
from audit_engine.semantic_audit.graph.backend.networkx_traversal import (
    NetworkXGraphTraversalEngine,
)
from audit_engine.semantic_audit.graph.service import SemanticGraphAnalysisService


BACKENDS = ("networkx", "scipy", "igraph", "graph-tool", "snap")
MODULES = {
    "networkx": "networkx",
    "scipy": "scipy",
    "igraph": "igraph",
    "graph-tool": "graph_tool",
}


@pytest.fixture(scope="module", autouse=True)
def _validate_backend_target():
    selected = os.environ.get("AE32C_M74_BACKEND")
    if selected is not None and selected not in BACKENDS:
        pytest.fail(f"unknown AE32C_M74_BACKEND target: {selected!r}")


def _require_backend(backend: str) -> None:
    selected = os.environ.get("AE32C_M74_BACKEND")
    if selected is not None and selected != backend:
        pytest.skip(f"workflow job targets {selected}, not {backend}")

    if backend == "snap":
        image = os.environ.get("AE32C_SNAP_WORKER_IMAGE")
        image_id = os.environ.get("AE32C_SNAP_WORKER_IMAGE_ID")
        if not image:
            if selected == backend:
                pytest.fail("G4 SNAP tests require AE32C_SNAP_WORKER_IMAGE")
            pytest.skip("G4 SNAP tests require the isolated worker environment")
        if not image_id or not image_id.startswith("sha256:"):
            pytest.fail("G4 SNAP tests require an immutable worker image ID")
        return

    try:
        available = find_spec(MODULES[backend]) is not None
    except (ImportError, ValueError):
        available = False
    if not available:
        if selected == backend:
            pytest.fail(f"configured G4 backend {backend!r} is not importable")
        pytest.skip(f"optional backend {backend!r} is not installed")


def _integrity_graph() -> SemanticGraph:
    graph = SemanticGraph()
    graph.add_node(SemanticNode(
        "A", "Module",
        {"nested": {"version": 1, "tags": ["canonical"]}},
        {"source": {"path": "src/a.py", "sha256": "a" * 64}},
    ))
    graph.add_node(SemanticNode(
        "B", "Module",
        {"nested": {"version": 1}},
        {"source": {"path": "src/b.py", "sha256": "b" * 64}},
    ))
    graph.add_node(SemanticNode(
        "C", "Module",
        {"nested": {"version": 1}},
        {"source": {"path": "src/c.py", "sha256": "c" * 64}},
    ))
    graph.add_edge(SemanticEdge(
        "A", "B", "IMPORTS",
        {"nested": {"occurrence": 1, "tags": ["first"]}},
        {"source": "src/a.py", "line": 10},
    ))
    graph.add_edge(SemanticEdge(
        "A", "B", "IMPORTS",
        {"nested": {"occurrence": 2, "tags": ["parallel"]}},
        {"source": "src/a.py", "line": 11},
    ))
    graph.add_edge(SemanticEdge(
        "B", "C", "DEPENDS_ON",
        {"nested": {"occurrence": 3}},
        {"source": "src/b.py", "line": 20},
    ))
    graph.add_edge(SemanticEdge(
        "C", "C", "SELF",
        {"nested": {"occurrence": 4}},
        {"source": "src/c.py", "line": 30},
    ))
    return graph


def _engine(graph: SemanticGraph, backend: str, *, verify_parity: bool = False):
    service = SemanticGraphAnalysisService(
        graph,
        traversal_backend=backend,
        verify_backend_parity=verify_parity,
    )
    engine = service.engine.traversal_engine
    if backend == "networkx":
        assert isinstance(engine, NetworkXGraphTraversalEngine)
    else:
        assert isinstance(engine, NativeAdapterGraphTraversalEngine)
    return engine


def _value(record, field: str):
    return getattr(record, field) if hasattr(record, field) else record[field]


def _node_id(record: object) -> str:
    return getattr(record, "node_id") if hasattr(record, "node_id") else record["id"]


def _close_worker(engine, backend: str) -> None:
    if backend == "snap":
        engine.adapter.close()


@pytest.mark.parametrize("backend", BACKENDS)
def test_g4_projection_snapshot_is_deeply_isolated_and_stale_canonical_fails_closed(backend):
    _require_backend(backend)
    graph = _integrity_graph()
    original = copy.deepcopy(graph.to_dict())
    engine = _engine(graph, backend)
    try:
        assert graph.to_dict() == original

        adapter = engine.adapter
        initial_nodes = tuple(adapter.iter_native_nodes())
        initial_edges = tuple(adapter.iter_adjacent_edge_occurrences(
            "A", TraversalDirection.OUTGOING,
        ))
        assert len(initial_nodes) == 3
        assert len(initial_edges) == 2
        node_a = next(item for item in initial_nodes if _node_id(item) == "A")
        assert _value(node_a, "attributes")["nested"]["version"] == 1
        assert {_value(item, "attributes")["nested"]["occurrence"] for item in initial_edges} == {1, 2}

        # Mutate nested caller-owned data after projection construction.
        graph.nodes[0].attributes["nested"]["version"] = 2
        graph.nodes[0].attributes["nested"]["tags"].append("caller-mutation")
        graph.edges[0].attributes["nested"]["tags"].append("caller-mutation")

        snapshot_nodes = tuple(adapter.iter_native_nodes())
        snapshot_edges = tuple(adapter.iter_adjacent_edge_occurrences(
            "A", TraversalDirection.OUTGOING,
        ))
        snapshot_a = next(item for item in snapshot_nodes if _node_id(item) == "A")
        assert _value(snapshot_a, "attributes")["nested"]["version"] == 1
        assert "caller-mutation" not in _value(snapshot_a, "attributes")["nested"]["tags"]
        assert "caller-mutation" not in _value(snapshot_edges[0], "attributes")["nested"]["tags"]

        with pytest.raises(RuntimeError, match="canonical_graph_changed"):
            engine.walk("A", direction="outgoing", max_depth=1)
    finally:
        _close_worker(engine, backend)


@pytest.mark.parametrize("backend", BACKENDS)
def test_g4_canonical_mutation_during_native_adjacency_query_fails_closed(backend, monkeypatch):
    _require_backend(backend)
    graph = _integrity_graph()
    engine = _engine(graph, backend, verify_parity=False)
    try:
        adapter = engine.adapter
        native_adjacency = adapter.iter_adjacent_edge_occurrences
        mutation_applied = False

        def mutate_canonical_after_native_read(node_id, direction):
            nonlocal mutation_applied
            records = tuple(native_adjacency(node_id, direction))
            if node_id == "A" and not mutation_applied:
                # Mutate an unreached node: the guard must be graph-wide, not
                # merely a check of the current node's local payload.
                graph.nodes[2].metadata["source"]["sha256"] = "f" * 64
                mutation_applied = True
            return records

        monkeypatch.setattr(
            adapter, "iter_adjacent_edge_occurrences",
            mutate_canonical_after_native_read,
        )
        with pytest.raises(RuntimeError, match="canonical_graph_changed_during"):
            engine.walk("A", direction="outgoing", max_depth=1)
        assert mutation_applied is True
        assert engine.runtime_report()["backend_execution"]["queries_failed"] == 1
    finally:
        _close_worker(engine, backend)


@pytest.mark.parametrize("backend", BACKENDS)
def test_g4_corrupted_local_edge_occurrence_payload_fails_closed(backend, monkeypatch):
    _require_backend(backend)
    graph = _integrity_graph()
    engine = _engine(graph, backend, verify_parity=False)
    try:
        adapter = engine.adapter
        native_adjacency = adapter.iter_adjacent_edge_occurrences

        def corrupt_one_occurrence(node_id, direction):
            records = tuple(native_adjacency(node_id, direction))
            if node_id == "A" and records:
                records = (
                    replace(records[0], metadata={"source": "tampered", "line": -1}),
                    *records[1:],
                )
            return records

        monkeypatch.setattr(
            adapter, "iter_adjacent_edge_occurrences", corrupt_one_occurrence,
        )
        with pytest.raises(RuntimeError, match="semantic.*mismatch"):
            engine.walk("A", direction="outgoing", max_depth=1)
        assert engine.runtime_report()["backend_execution"]["queries_failed"] == 1
    finally:
        _close_worker(engine, backend)


@pytest.mark.parametrize("backend", BACKENDS)
def test_g4_missing_native_occurrence_is_rejected_by_reference_parity(backend, monkeypatch):
    _require_backend(backend)
    graph = _integrity_graph()
    engine = _engine(graph, backend, verify_parity=True)
    try:
        monkeypatch.setattr(
            engine.adapter, "iter_adjacent_edge_occurrences",
            lambda node_id, direction: (),
        )
        with pytest.raises(RuntimeError, match="parity_mismatch"):
            engine.walk("A", direction="outgoing", max_depth=1)
        assert engine.runtime_report()["backend_execution"]["queries_failed"] == 1
        assert engine.runtime_report()["backend_execution"]["parity_failures"] == 1
    finally:
        _close_worker(engine, backend)


@pytest.mark.parametrize("backend", BACKENDS)
def test_g4_repeated_queries_and_fresh_projection_reconstruction_are_stable(backend):
    _require_backend(backend)
    graph = _integrity_graph()
    canonical_before = copy.deepcopy(graph.to_dict())
    engine = _engine(graph, backend, verify_parity=True)
    reconstructed = None
    try:
        first = engine.walk("A", direction="outgoing", max_depth=2)
        second = engine.walk("A", direction="outgoing", max_depth=2)
        assert first == second
        assert engine.runtime_report()["backend_execution"]["queries_succeeded"] == 2

        reconstructed = _engine(graph, backend, verify_parity=True)
        third = reconstructed.walk("A", direction="outgoing", max_depth=2)
        assert third == first
        assert graph.to_dict() == canonical_before

        if backend == "snap":
            engine.adapter.close()
            with pytest.raises(RuntimeError, match="snap_worker_process_not_running"):
                engine.walk("A", direction="outgoing", max_depth=2)
    finally:
        if reconstructed is not None:
            _close_worker(reconstructed, backend)
        _close_worker(engine, backend)
