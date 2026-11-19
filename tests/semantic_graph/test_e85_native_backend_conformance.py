"""E.8.5 native backend conformance tests.

Actual optional native libraries are tested when installed. Their absence is
reported as a skip here; the dedicated E.8.5 GitHub workflow provisions the
supported native environments separately. Mocked adapters are not counted as
native conformance.
"""
from __future__ import annotations

from importlib.util import find_spec

import pytest

from tools.gb03_native_backend_conformance import (
    BACKENDS,
    fixture,
    probe_backend,
    run,
)


@pytest.mark.parametrize("backend", BACKENDS)
def test_backend_probe_never_claims_native_conformance_without_execution(backend):
    report = probe_backend(backend)
    assert report["backend"] == backend
    assert report["status"] in {"available", "not_installed", "incompatible"}
    assert report["native_conformance"] == "not_run"


def test_conformance_fixture_contains_required_semantic_edge_cases():
    graph = fixture()
    assert len(graph.nodes) == 5
    assert len(graph.edges) == 8
    parallel = [
        edge for edge in graph.edges
        if edge.source_id == "alpha" and edge.target_id == "beta"
    ]
    assert len(parallel) == 3
    assert sum(edge.source_id == edge.target_id for edge in graph.edges) == 1
    assert any("λ" in str(node.attributes) for node in graph.nodes)
    assert any("雪" in str(edge.metadata) for edge in graph.edges)


@pytest.mark.parametrize("backend", BACKENDS)
def test_native_backend_conformance_when_library_is_installed(backend):
    module = {
        "networkx": "networkx",
        "scipy": "scipy",
        "igraph": "igraph",
        "graph-tool": "graph_tool",
        "snap": "snap",
    }[backend]
    if find_spec(module) is None:
        pytest.skip(f"{backend} native library is not installed in this interpreter")

    report = run(backend)
    assert report["status"] == "passed"
    assert report["backend"] == backend
    assert report["case_count"] == 7
    assert report["projection_round_trip"]["exact"] is True
    assert report["projection_round_trip"]["node_count"] == 5
    assert report["projection_round_trip"]["edge_occurrence_count"] == 8
    assert report["backend_execution"]["parity_verified_queries"] == 14
    assert report["backend_execution"]["parity_failures"] == 0
    assert report["backend_execution"]["queries_failed"] == 0
    assert report["provider_calls"] == 0
    assert report["network_calls"] == 0


def test_networkx_and_scipy_round_trip_same_canonical_semantic_payload():
    networkx = run("networkx")
    scipy = run("scipy")
    assert networkx["projection_round_trip"]["round_trip_sha256"] == (
        scipy["projection_round_trip"]["round_trip_sha256"]
    )
    assert networkx["canonical_graph_fingerprint"] == scipy["canonical_graph_fingerprint"]


def test_snap_adapter_is_not_marked_native_verified_by_presence_alone():
    report = probe_backend("snap")
    assert report["native_conformance"] == "not_run"
    if report["status"] != "available":
        assert report["status"] in {"not_installed", "incompatible"}
