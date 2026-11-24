"""M7.4 task-level semantic acceptance tests.

These tests exercise the public analysis service for STRUCTURAL, DEPENDENCY and
PATH queries. A passing test establishes bounded semantic parity and observed
native-path execution for the tested environment; it is not, by itself, a
backend suitability verdict or production approval.
"""
from __future__ import annotations

import os
from importlib.util import find_spec

import pytest

from audit_engine.semantic_audit.core.semantic_graph import (
    SemanticEdge,
    SemanticGraph,
    SemanticNode,
)
from audit_engine.semantic_audit.graph.analysis import AnalysisStatus
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.graph.service import SemanticGraphAnalysisService


BACKENDS = ("networkx", "scipy", "igraph", "graph-tool", "snap")
TASKS = ("structural", "dependency", "path")
MODULES = {
    "networkx": "networkx",
    "scipy": "scipy",
    "igraph": "igraph",
    "graph-tool": "graph_tool",
}
NATIVE_QUERY_MODES = {
    "networkx": "networkx_successor_predecessor_adjacency",
    "scipy": "scipy_csr_csc_adjacency",
    "igraph": "igraph_incident_edge_ids",
    "graph-tool": "graph_tool_vertex_edge_iterators",
    "snap": "snap_isolated_worker_tneanet_edge_ids",
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
                pytest.fail("SNAP task assessment requires AE32C_SNAP_WORKER_IMAGE")
            pytest.skip("SNAP task assessment requires the isolated worker environment")
        if not image_id or not image_id.startswith("sha256:"):
            pytest.fail("SNAP task assessment requires a recorded immutable worker image ID")
        return

    module = MODULES[backend]
    try:
        available = find_spec(module) is not None
    except (ImportError, ValueError):
        available = False
    if not available:
        if selected == backend:
            pytest.fail(f"configured M7.4 backend {backend!r} is not importable")
        pytest.skip(f"optional backend {backend!r} is not installed in this environment")


def _assessment_graph() -> SemanticGraph:
    graph = SemanticGraph()
    for node_id in ("A", "B", "C", "D", "E"):
        graph.add_node(SemanticNode(node_id, "AssessmentNode"))

    # Two distinct occurrences with the same endpoints and predicate ensure
    # that the analyzer preserves occurrence identity rather than collapsing
    # a multigraph into a set of endpoint pairs.
    graph.add_edge(SemanticEdge(
        "A", "B", "IMPORTS", {"ordinal": 1}, {"source": "a.py", "line": 10},
    ))
    graph.add_edge(SemanticEdge(
        "A", "B", "IMPORTS", {"ordinal": 2}, {"source": "a.py", "line": 11},
    ))
    # This direct edge is intentionally outside the dependency/path relation
    # scope. It must not become a false one-hop dependency or shorter path.
    graph.add_edge(SemanticEdge(
        "A", "C", "USES", {"ordinal": 3}, {"source": "a.py", "line": 12},
    ))
    graph.add_edge(SemanticEdge(
        "B", "D", "DEPENDS_ON", {"ordinal": 4}, {"source": "b.py", "line": 20},
    ))
    graph.add_edge(SemanticEdge(
        "D", "C", "IMPORTS", {"ordinal": 5}, {"source": "d.py", "line": 30},
    ))
    graph.add_edge(SemanticEdge(
        "E", "A", "IMPORTS", {"ordinal": 6}, {"source": "e.py", "line": 40},
    ))
    graph.add_edge(SemanticEdge(
        "C", "C", "SELF", {"ordinal": 7}, {"source": "c.py", "line": 50},
    ))
    return graph


def _query(task: str) -> GraphQuery:
    if task == "structural":
        return GraphQuery(
            "m74-structural-outgoing",
            QueryType.STRUCTURAL,
            ["A"],
            {"direction": "outgoing", "relation_types": ["IMPORTS"]},
        )
    if task == "dependency":
        return GraphQuery(
            "m74-dependency-transitive",
            QueryType.DEPENDENCY,
            ["A"],
            {
                "direction": "outgoing",
                "relation_types": ["IMPORTS", "DEPENDS_ON"],
                "max_depth": 3,
            },
        )
    if task == "path":
        return GraphQuery(
            "m74-path-bounded",
            QueryType.PATH,
            ["A"],
            {
                "target_entity": "C",
                "direction": "outgoing",
                "relation_types": ["IMPORTS", "DEPENDS_ON"],
                "max_depth": 3,
            },
        )
    raise AssertionError(f"unknown M7.4 task: {task}")


def _semantic_metadata(result) -> dict:
    return {
        key: value
        for key, value in result.metadata.items()
        if not key.startswith("backend_") and key != "computation_backend"
    }


def _assert_reference_equivalence(actual, reference) -> None:
    assert actual.analysis_id == reference.analysis_id
    assert actual.query_id == reference.query_id
    assert actual.analysis_type == reference.analysis_type
    assert actual.status == reference.status
    assert actual.algorithm == reference.algorithm
    assert actual.graph_fingerprint == reference.graph_fingerprint
    assert actual.source_entities == reference.source_entities
    assert actual.discovered_entities == reference.discovered_entities
    assert actual.observations == reference.observations
    assert actual.evidence == reference.evidence
    assert actual.parameters == reference.parameters
    assert _semantic_metadata(actual) == _semantic_metadata(reference)


def _assert_native_execution(service, result, backend: str) -> None:
    assert result.metadata["computation_backend"] == backend
    assert result.metadata["backend_library"] == backend
    assert result.metadata["backend_native_query_mode"] == NATIVE_QUERY_MODES[backend]
    assert result.metadata["backend_parity_status"] == "verified_against_reference_per_query"

    native_metrics = result.metadata["backend_native_query_metrics"]
    assert native_metrics["native_adjacency_lookups"] > 0
    assert native_metrics["native_edge_occurrences_read"] > 0

    runtime = service.engine.traversal_engine.runtime_report()
    execution = runtime["backend_execution"]
    assert execution["queries_attempted"] == 1
    assert execution["queries_succeeded"] == 1
    assert execution["queries_failed"] == 0
    assert execution["parity_verified_queries"] == 1
    assert execution["parity_failures"] == 0


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("task", TASKS)
def test_m74_public_analyzer_path_matches_reference_and_uses_native_backend(backend, task):
    _require_backend(backend)
    graph = _assessment_graph()
    before = graph.to_dict()
    query = _query(task)

    service = SemanticGraphAnalysisService(
        graph, traversal_backend=backend, verify_backend_parity=True,
    )
    reference = SemanticGraphAnalysisService(
        graph, traversal_backend="reference", verify_backend_parity=True,
    )

    result = service.analyze(query)
    expected = reference.analyze(query)

    _assert_reference_equivalence(result, expected)
    _assert_native_execution(service, result, backend)
    assert graph.to_dict() == before

    if task == "structural":
        assert result.status is AnalysisStatus.COMPLETED
        assert result.discovered_entities == ("B",)
        assert len(result.evidence) == 2
        assert {
            record.provenance["edge_metadata"]["line"]
            for record in result.evidence
        } == {10, 11}
        assert {
            (item.subject_id, item.predicate, item.object_id)
            for item in result.observations
        } == {("A", "IMPORTS", "B")}

    elif task == "dependency":
        assert result.status is AnalysisStatus.COMPLETED
        assert result.discovered_entities == ("B", "D", "C")
        assert len(result.evidence) == 4
        assert {
            (item.subject_id, item.predicate, item.object_id)
            for item in result.observations
        } == {
            ("A", "IMPORTS", "B"),
            ("B", "DEPENDS_ON", "D"),
            ("D", "IMPORTS", "C"),
        }
        assert "USES" not in {record.predicate for record in result.evidence}

    else:
        assert result.status is AnalysisStatus.COMPLETED
        assert result.metadata["path_length"] == 3
        assert [
            (item.subject_id, item.predicate, item.object_id)
            for item in result.observations
        ] == [
            ("A", "IMPORTS", "B"),
            ("B", "DEPENDS_ON", "D"),
            ("D", "IMPORTS", "C"),
        ]
        assert len(result.evidence) == 3
        assert all(record.predicate != "USES" for record in result.evidence)


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize(
    ("source", "constraints", "expected_nodes", "expected_edges"),
    [
        (
            "A",
            {"direction": "incoming", "relation_types": ["IMPORTS"]},
            ("E",),
            {("E", "IMPORTS", "A")},
        ),
        (
            "C",
            {"direction": "both", "relation_types": ["IMPORTS", "SELF"]},
            ("D",),
            {("D", "IMPORTS", "C"), ("C", "SELF", "C")},
        ),
    ],
)
def test_m74_structural_direction_and_self_loop_semantics(
    backend, source, constraints, expected_nodes, expected_edges,
):
    _require_backend(backend)
    graph = _assessment_graph()
    before = graph.to_dict()
    query = GraphQuery(
        f"m74-structural-{source}-{constraints['direction']}",
        QueryType.STRUCTURAL,
        [source],
        constraints,
    )
    service = SemanticGraphAnalysisService(
        graph, traversal_backend=backend, verify_backend_parity=True,
    )
    reference = SemanticGraphAnalysisService(
        graph, traversal_backend="reference", verify_backend_parity=True,
    )
    result = service.analyze(query)

    _assert_reference_equivalence(result, reference.analyze(query))
    _assert_native_execution(service, result, backend)
    assert result.status is AnalysisStatus.COMPLETED
    assert result.discovered_entities == expected_nodes
    observed = [
        (item.subject_id, item.predicate, item.object_id)
        for item in result.observations
    ]
    assert set(observed) == expected_edges
    if source == "C":
        assert observed.count(("C", "SELF", "C")) == 1
    assert graph.to_dict() == before


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("task", ("dependency", "path"))
def test_m74_bounded_queries_report_incomplete_instead_of_false_completion(backend, task):
    _require_backend(backend)
    graph = _assessment_graph()
    before = graph.to_dict()
    if task == "dependency":
        query = GraphQuery(
            "m74-dependency-step-bound",
            QueryType.DEPENDENCY,
            ["A"],
            {
                "direction": "outgoing",
                "relation_types": ["IMPORTS", "DEPENDS_ON"],
                "max_depth": 3,
                "max_traversal_steps": 2,
            },
        )
    else:
        query = GraphQuery(
            "m74-path-step-bound",
            QueryType.PATH,
            ["A"],
            {
                "target_entity": "C",
                "direction": "outgoing",
                "relation_types": ["IMPORTS", "DEPENDS_ON"],
                "max_depth": 3,
                "max_traversal_steps": 2,
            },
        )

    service = SemanticGraphAnalysisService(
        graph, traversal_backend=backend, verify_backend_parity=True,
    )
    reference = SemanticGraphAnalysisService(
        graph, traversal_backend="reference", verify_backend_parity=True,
    )
    result = service.analyze(query)

    _assert_reference_equivalence(result, reference.analyze(query))
    _assert_native_execution(service, result, backend)
    assert result.status is AnalysisStatus.INCOMPLETE
    assert result.metadata["truncated"] is True
    assert result.metadata["stop_reason"] == "max_traversal_steps"
    assert result.metadata["examined_edges"] == 2
    if task == "path":
        assert result.observations == ()
        assert result.evidence == ()
    else:
        assert result.discovered_entities == ("B",)
    assert graph.to_dict() == before
