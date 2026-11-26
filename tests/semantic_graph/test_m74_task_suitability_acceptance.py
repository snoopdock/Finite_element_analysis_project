"""M7.4 task-level semantic acceptance tests.

These tests exercise all four public analysis service routes and extend the
synthetic fixtures with seeded, bounded M7.2 topology workloads. A passing test
establishes task-scoped parity and observed native-path execution for the tested
input envelope; it is not, by itself, a backend suitability verdict or
production approval.
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



def _m74_impact_graph() -> SemanticGraph:
    graph = SemanticGraph()
    nodes = [
        ("file:src/app.py", "PythonSourceFile", {"path": "src/app.py"}),
        ("module:app", "PythonModule", {"path": "src/app.py"}),
        ("symbol:app.run", "PythonSymbol", {"path": "src/app.py", "name": "run"}),
        ("file:src/lib.py", "PythonSourceFile", {"path": "src/lib.py"}),
        ("module:lib", "PythonModule", {"path": "src/lib.py"}),
        ("module:consumer", "PythonModule", {"path": "src/consumer.py"}),
        ("module:consumer2", "PythonModule", {"path": "src/consumer2.py"}),
        ("symbol:caller", "PythonSymbol", {"path": "src/consumer.py", "name": "caller"}),
        ("file:tests/test_app.py", "TestFile", {"path": "tests/test_app.py"}),
        ("file:.github/workflows/ci.yml", "WorkflowFile", {"path": ".github/workflows/ci.yml"}),
    ]
    for node_id, kind, attributes in nodes:
        graph.add_node(SemanticNode(
            node_id, kind, attributes,
            {"source_sha256": f"sha-{node_id}"},
        ))

    edges = [
        ("file:src/app.py", "module:app", "IMPLEMENTS"),
        ("module:app", "file:src/app.py", "IMPLEMENTED_BY"),
        ("file:src/app.py", "symbol:app.run", "DEFINES"),
        ("symbol:app.run", "module:app", "MEMBER_OF"),
        ("file:src/lib.py", "module:lib", "IMPLEMENTS"),
        ("module:lib", "file:src/lib.py", "IMPLEMENTED_BY"),
        ("module:app", "module:lib", "IMPORTS"),
        ("module:lib", "module:app", "DEPENDS_ON"),
        ("module:consumer", "module:app", "IMPORTS"),
        ("module:consumer2", "module:consumer", "IMPORTS"),
        ("symbol:caller", "symbol:app.run", "CALLS"),
        ("file:tests/test_app.py", "module:app", "TESTS"),
        ("file:.github/workflows/ci.yml", "module:app", "INVOKES"),
    ]
    for ordinal, (source, target, relation) in enumerate(edges, start=1):
        graph.add_edge(SemanticEdge(
            source, target, relation,
            {"ordinal": ordinal},
            {"path": f"evidence/{ordinal}.py", "line": ordinal},
        ))
    return graph


def _m74_impact_query(
    sources=("file:src/app.py", "file:src/lib.py"),
    **constraints,
) -> GraphQuery:
    return GraphQuery(
        "m74-impact-change-set",
        QueryType.IMPACT,
        sources,
        {
            "max_depth": 4,
            "max_visited_nodes": 40,
            "max_traversal_steps": 500,
            **constraints,
        },
    )


def _assert_m74_impact_native_execution(service, result, backend: str) -> None:
    assert result.metadata["computation_backend"] == backend
    assert result.metadata["backend_library"] == backend
    assert result.metadata["backend_parity_status"] == "verified_against_reference_per_query"
    expected_mode = NATIVE_QUERY_MODES[backend]
    assert result.metadata["backend_native_query_mode"] == expected_mode

    runtime = service.engine.traversal_engine.runtime_report()
    execution = runtime["backend_execution"]
    assert execution["queries_attempted"] > 1
    assert execution["queries_succeeded"] == execution["queries_attempted"]
    assert execution["queries_failed"] == 0
    assert execution["parity_verified_queries"] == execution["queries_attempted"]
    assert execution["parity_failures"] == 0
    assert execution["native_adjacency_lookups"] > 0
    assert execution["native_edge_occurrences_read"] > 0


@pytest.mark.parametrize("backend", BACKENDS)
def test_m74_impact_multi_source_attribution_ownership_and_cycle_evidence(backend):
    _require_backend(backend)
    graph = _m74_impact_graph()
    before = graph.to_dict()
    query = _m74_impact_query()
    service = SemanticGraphAnalysisService(
        graph, traversal_backend=backend, verify_backend_parity=True,
    )
    reference = SemanticGraphAnalysisService(
        graph, traversal_backend="reference", verify_backend_parity=True,
    )

    result = service.analyze(query)
    expected = reference.analyze(query)
    reverse_order = reference.analyze(_m74_impact_query(
        ("file:src/lib.py", "file:src/app.py"),
    ))

    _assert_reference_equivalence(result, expected)
    _assert_m74_impact_native_execution(service, result, backend)
    assert result.status is AnalysisStatus.COMPLETED
    assert result.source_entities == ("file:src/app.py", "file:src/lib.py")
    assert result.analysis_id == reverse_order.analysis_id
    assert result.discovered_entities == reverse_order.discovered_entities
    assert result.metadata["impact_candidates"] == reverse_order.metadata["impact_candidates"]
    assert result.metadata["dependency_cycles"] == reverse_order.metadata["dependency_cycles"]

    metadata = result.metadata
    assert metadata["changed_source_count"] == 2
    assert metadata["unique_impact_count"] == len(metadata["impact_candidates"])
    assert metadata["unique_impact_count"] == len(result.discovered_entities)
    assert metadata["shared_impact_count"] >= 1
    shared = {
        item["node_id"]: item
        for item in metadata["impact_candidates"]
        if item["shared_change_impact"]
    }
    assert "module:consumer" in shared
    assert shared["module:consumer"]["affected_by"] == [
        "file:src/app.py", "file:src/lib.py",
    ]
    assert set(shared["module:consumer"]["paths_by_source"]) == {
        "file:src/app.py", "file:src/lib.py",
    }
    assert all(
        shared["module:consumer"]["paths_by_source"][source]
        for source in ("file:src/app.py", "file:src/lib.py")
    )
    assert "file:tests/test_app.py" in metadata["affected_test_candidate_ids"]
    assert "file:.github/workflows/ci.yml" in metadata["affected_workflow_candidate_ids"]
    assert "symbol:caller" in metadata["affected_symbol_candidate_ids"]

    evidence_by_id = {item.evidence_id: item for item in result.evidence}
    ownership_ids = set(metadata["ownership_evidence_ids"])
    assert ownership_ids
    assert ownership_ids.issubset(evidence_by_id)
    # File-source ownership resolution is depth one; MEMBER_OF is a second-hop edge.
    assert {"IMPLEMENTS", "IMPLEMENTED_BY", "DEFINES"}.issubset({
        evidence_by_id[item].predicate for item in ownership_ids
    })

    assert metadata["cycle_analysis_status"] == "complete"
    assert metadata["cycle_scan_edge_count"] == len(graph.edges)
    assert metadata["dependency_cycle_count"] == 1
    cycle = metadata["dependency_cycles"][0]
    assert cycle["node_ids"] == ["module:app", "module:lib"]
    assert cycle["relation_types"] == ["DEPENDS_ON", "IMPORTS"]
    assert cycle["edge_count"] == 2
    assert set(cycle["evidence_ids"]).issubset(evidence_by_id)
    assert any(
        item["code"] == "dependency_cycle_observed"
        for item in metadata["risk_indicators"]
    )

    assert metadata["runtime_execution_proven"] is False
    assert metadata["severity_assessed"] is False
    assert metadata["semantic_correctness_assessed"] is False
    assert metadata["automatic_approval_permitted"] is False
    assert metadata["authoritative_graph_mutation_permitted"] is False
    assert graph.to_dict() == before


@pytest.mark.parametrize("backend", BACKENDS)
def test_m74_impact_global_change_set_budgets_are_deterministic_and_incomplete(backend):
    _require_backend(backend)
    graph = _m74_impact_graph()
    before = graph.to_dict()
    query = _m74_impact_query(
        max_visited_nodes=4,
        max_traversal_steps=4,
    )
    service = SemanticGraphAnalysisService(
        graph, traversal_backend=backend, verify_backend_parity=True,
    )
    reference = SemanticGraphAnalysisService(
        graph, traversal_backend="reference", verify_backend_parity=True,
    )
    result = service.analyze(query)

    _assert_reference_equivalence(result, reference.analyze(query))
    _assert_m74_impact_native_execution(service, result, backend)
    assert result.status is AnalysisStatus.INCOMPLETE
    assert result.metadata["truncated"] is True
    assert "impact_frontier_incomplete" in {
        item["code"] for item in result.metadata["risk_indicators"]
    }
    assert result.metadata["examined_edges"] <= 4
    per_source = result.metadata["per_source_visited_node_counts"]
    assert set(per_source) == {"file:src/app.py", "file:src/lib.py"}
    assert all(count <= 2 for count in per_source.values())
    assert sum(per_source.values()) <= 4
    assert graph.to_dict() == before


@pytest.mark.parametrize("backend", BACKENDS)
def test_m74_impact_cycle_scan_budget_is_explicitly_incomplete(backend, monkeypatch):
    _require_backend(backend)
    from audit_engine.semantic_audit.graph.analysis.impact import ImpactAnalyzer

    monkeypatch.setattr(ImpactAnalyzer, "MAX_CYCLE_SCAN_EDGES", 1)
    graph = _m74_impact_graph()
    before = graph.to_dict()
    service = SemanticGraphAnalysisService(
        graph, traversal_backend=backend, verify_backend_parity=True,
    )
    result = service.analyze(_m74_impact_query())

    _assert_m74_impact_native_execution(service, result, backend)
    assert result.status is AnalysisStatus.INCOMPLETE
    assert result.metadata["cycle_analysis_status"] == "incomplete_edge_limit"
    assert result.metadata["cycle_scan_edge_count"] == 0
    assert any(
        item["code"] == "dependency_cycle_scan_incomplete"
        for item in result.metadata["risk_indicators"]
    )
    assert graph.to_dict() == before


@pytest.mark.parametrize("backend", BACKENDS)
def test_m74_impact_duplicate_and_oversized_change_sets_fail_closed(backend):
    _require_backend(backend)
    from audit_engine.semantic_audit.graph.queries.validation import GraphQueryValidationError

    graph = SemanticGraph()
    source_ids = tuple(f"change:{index}" for index in range(26))
    for source_id in source_ids:
        graph.add_node(SemanticNode(source_id, "ChangeSource"))
    service = SemanticGraphAnalysisService(graph, traversal_backend=backend)

    with pytest.raises(GraphQueryValidationError, match="duplicate"):
        service.analyze(GraphQuery(
            "m74-impact-duplicates",
            QueryType.IMPACT,
            ("change:0", "change:0"),
        ))
    with pytest.raises(GraphQueryValidationError, match="limited to 25"):
        service.analyze(GraphQuery(
            "m74-impact-over-limit",
            QueryType.IMPACT,
            source_ids,
        ))



def _m74_replicate_seeded_workload(base_graph: SemanticGraph, replicas: int = 3) -> SemanticGraph:
    """Replicate a seeded topology without changing its per-component shape."""
    expanded = SemanticGraph()
    for replica in range(replicas):
        id_map = {
            node.node_id: f"replica-{replica}:{node.node_id}"
            for node in base_graph.nodes
        }
        for node in base_graph.nodes:
            expanded.add_node(SemanticNode(
                id_map[node.node_id],
                node.entity_type,
                dict(node.attributes),
                {**dict(node.metadata), "replica": replica},
            ))
        for edge in base_graph.edges:
            expanded.add_edge(SemanticEdge(
                id_map[edge.source_id],
                id_map[edge.target_id],
                edge.relation_type,
                dict(edge.attributes),
                {**dict(edge.metadata), "replica": replica},
            ))
    return expanded


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize(
    "workload_id",
    (
        "sparse_dependency",
        "hub_impact",
        "parallel_evidence",
        "disconnected_components",
        "dense_local_neighborhood",
    ),
)
@pytest.mark.parametrize("seed", (20261101, 20261102))
def test_m74_seeded_topology_workloads_cover_all_public_analysis_tasks(
    backend, workload_id, seed,
):
    """Exercise the four public analyzers on M7.2 topology families at larger size."""
    _require_backend(backend)
    from tools import gb06_task_suitability_campaign as m72
    from audit_engine.semantic_audit.graph.analysis.traversal import GraphTraversalEngine
    from audit_engine.semantic_audit.graph.analysis.models import TraversalDirection

    base_graph = m72._make_graph(workload_id, seed)
    graph = _m74_replicate_seeded_workload(base_graph, replicas=3)
    before = graph.to_dict()
    base_node_ids = [node.node_id for node in base_graph.nodes]
    source = f"replica-0:{base_node_ids[0]}"
    second_source = f"replica-0:{base_node_ids[min(8, len(base_node_ids) - 1)]}"
    relation_types = [
        "DEPENDS_ON", "CITES", "DERIVED_FROM", "SUPPORTS",
    ]
    max_visited = len(graph.nodes)
    max_steps = min(10000, max(2, len(graph.edges) * 2))

    # Pick a path target from the reference traversal itself, then require the
    # public PATH analyzer and each backend to reproduce that same path result.
    probe = GraphTraversalEngine(graph).walk(
        source,
        direction=TraversalDirection.OUTGOING,
        relation_types=tuple(relation_types),
        max_depth=6,
    )
    assert probe.visited_nodes, f"seeded workload has no reachable node: {workload_id}/{seed}"
    path_target = probe.visited_nodes[-1]

    queries = (
        GraphQuery(
            f"m74-{workload_id}-{seed}-structural",
            QueryType.STRUCTURAL,
            (source,),
            {
                "direction": "outgoing",
                "relation_types": relation_types,
            },
        ),
        GraphQuery(
            f"m74-{workload_id}-{seed}-dependency",
            QueryType.DEPENDENCY,
            (source,),
            {
                "direction": "outgoing",
                "relation_types": relation_types,
                "max_depth": 6,
                "max_visited_nodes": max_visited,
                "max_traversal_steps": max_steps,
            },
        ),
        GraphQuery(
            f"m74-{workload_id}-{seed}-path",
            QueryType.PATH,
            (source,),
            {
                "target_entity": path_target,
                "direction": "outgoing",
                "relation_types": relation_types,
                "max_depth": 6,
                "max_visited_nodes": max_visited,
                "max_traversal_steps": max_steps,
            },
        ),
        GraphQuery(
            f"m74-{workload_id}-{seed}-impact",
            QueryType.IMPACT,
            (source, second_source),
            {
                "relation_types": relation_types,
                "max_depth": 5,
                "max_visited_nodes": min(2000, len(graph.nodes) * 2),
                "max_traversal_steps": min(10000, max(2, len(graph.edges) * 4)),
            },
        ),
    )

    service = SemanticGraphAnalysisService(
        graph, traversal_backend=backend, verify_backend_parity=True,
    )
    reference = SemanticGraphAnalysisService(
        graph, traversal_backend="reference", verify_backend_parity=True,
    )

    for query in queries:
        result = service.analyze(query)
        expected = reference.analyze(query)
        _assert_reference_equivalence(result, expected)
        assert result.metadata["computation_backend"] == backend
        assert result.metadata["backend_library"] == backend
        assert result.metadata["backend_native_query_mode"] == NATIVE_QUERY_MODES[backend]
        assert result.metadata["backend_parity_status"] == "verified_against_reference_per_query"
        native_metrics = result.metadata["backend_native_query_metrics"]
        assert native_metrics["native_adjacency_lookups"] > 0
        assert native_metrics["native_edge_occurrences_read"] > 0

    runtime = service.engine.traversal_engine.runtime_report()
    execution = runtime["backend_execution"]
    assert execution["queries_attempted"] >= len(queries)
    assert execution["queries_succeeded"] == execution["queries_attempted"]
    assert execution["queries_failed"] == 0
    assert execution["parity_verified_queries"] == execution["queries_attempted"]
    assert execution["parity_failures"] == 0
    assert execution["native_adjacency_lookups"] > 0
    assert execution["native_edge_occurrences_read"] > 0
    assert graph.to_dict() == before


def _m74_fem_repository_graph() -> SemanticGraph:
    """Small domain-shaped FEM repository graph with explicit evidence paths."""
    graph = SemanticGraph()
    nodes = [
        ("file:src/fem/mesh.py", "PythonSourceFile", {"path": "src/fem/mesh.py"}),
        ("module:fem.mesh", "PythonModule", {"path": "src/fem/mesh.py"}),
        ("file:src/fem/solver.py", "PythonSourceFile", {"path": "src/fem/solver.py"}),
        ("module:fem.solver", "PythonModule", {"path": "src/fem/solver.py"}),
        ("file:src/fem/materials.py", "PythonSourceFile", {"path": "src/fem/materials.py"}),
        ("module:fem.materials", "PythonModule", {"path": "src/fem/materials.py"}),
        ("symbol:fem.materials.relative_permeability", "PythonSymbol", {
            "path": "src/fem/materials.py", "name": "relative_permeability",
        }),
        ("evidence:docs/constitutive-assumptions.md", "EvidenceRecord", {
            "path": "docs/constitutive-assumptions.md", "claim": "relative permeability",
        }),
        ("file:tests/test_solver.py", "TestFile", {"path": "tests/test_solver.py"}),
        ("file:.github/workflows/fem-validation.yml", "WorkflowFile", {
            "path": ".github/workflows/fem-validation.yml",
        }),
        ("module:fem.postprocess", "PythonModule", {"path": "src/fem/postprocess.py"}),
        ("module:fem.reporting", "PythonModule", {"path": "src/fem/reporting.py"}),
    ]
    for node_id, kind, attributes in nodes:
        graph.add_node(SemanticNode(
            node_id, kind, attributes,
            {"source_sha256": f"sha-{node_id}", "snapshot": "fem-repository-fixture-v1"},
        ))

    edges = [
        ("file:src/fem/mesh.py", "module:fem.mesh", "IMPLEMENTS"),
        ("module:fem.mesh", "file:src/fem/mesh.py", "IMPLEMENTED_BY"),
        ("file:src/fem/solver.py", "module:fem.solver", "IMPLEMENTS"),
        ("module:fem.solver", "file:src/fem/solver.py", "IMPLEMENTED_BY"),
        ("file:src/fem/materials.py", "module:fem.materials", "IMPLEMENTS"),
        ("module:fem.materials", "file:src/fem/materials.py", "IMPLEMENTED_BY"),
        ("module:fem.mesh", "module:fem.solver", "IMPORTS"),
        ("module:fem.solver", "module:fem.materials", "IMPORTS"),
        ("module:fem.solver", "module:fem.mesh", "DEPENDS_ON"),
        ("module:fem.materials", "symbol:fem.materials.relative_permeability", "DEFINES"),
        ("symbol:fem.materials.relative_permeability", "module:fem.materials", "MEMBER_OF"),
        ("module:fem.materials", "evidence:docs/constitutive-assumptions.md", "SUPPORTED_BY"),
        ("file:tests/test_solver.py", "module:fem.solver", "TESTS"),
        ("file:.github/workflows/fem-validation.yml", "module:fem.solver", "INVOKES"),
        ("module:fem.postprocess", "module:fem.solver", "IMPORTS"),
        ("module:fem.reporting", "module:fem.postprocess", "IMPORTS"),
    ]
    for ordinal, (source, target, relation) in enumerate(edges, start=1):
        graph.add_edge(SemanticEdge(
            source, target, relation,
            {"ordinal": ordinal},
            {"path": f"evidence/fem-repository/{ordinal}.json", "line": ordinal},
        ))
    return graph


@pytest.mark.parametrize("backend", BACKENDS)
def test_m74_fem_repository_workload_exercises_all_public_audit_tasks(backend):
    """Exercise task-shaped repository/FEM evidence paths, not only generic topology."""
    _require_backend(backend)
    graph = _m74_fem_repository_graph()
    before = graph.to_dict()
    evidence_target = "evidence:docs/constitutive-assumptions.md"
    queries = (
        GraphQuery(
            "m74-fem-structural-neighborhood",
            QueryType.STRUCTURAL,
            ("module:fem.solver",),
            {"direction": "outgoing", "relation_types": ("IMPORTS",)},
        ),
        GraphQuery(
            "m74-fem-dependency-context",
            QueryType.DEPENDENCY,
            ("module:fem.mesh",),
            {
                "direction": "outgoing",
                "relation_types": ("IMPORTS", "DEPENDS_ON"),
                "max_depth": 4,
                "max_visited_nodes": 32,
                "max_traversal_steps": 128,
            },
        ),
        GraphQuery(
            "m74-fem-claim-evidence-path",
            QueryType.PATH,
            ("module:fem.mesh",),
            {
                "target_entity": evidence_target,
                "direction": "outgoing",
                "relation_types": ("IMPORTS", "DEPENDS_ON", "SUPPORTED_BY"),
                "max_depth": 4,
                "max_visited_nodes": 32,
                "max_traversal_steps": 128,
            },
        ),
        GraphQuery(
            "m74-fem-change-impact",
            QueryType.IMPACT,
            ("file:src/fem/materials.py",),
            {
                "max_depth": 5,
                "max_visited_nodes": 32,
                "max_traversal_steps": 256,
            },
        ),
    )
    results = {}
    for query in queries:
        service = SemanticGraphAnalysisService(
            graph, traversal_backend=backend, verify_backend_parity=True,
        )
        reference = SemanticGraphAnalysisService(
            graph, traversal_backend="reference", verify_backend_parity=True,
        )
        actual = service.analyze(query)
        expected = reference.analyze(query)
        _assert_reference_equivalence(actual, expected)
        assert actual.status is AnalysisStatus.COMPLETED
        results[query.query_type] = actual
        if query.query_type is QueryType.IMPACT:
            _assert_m74_impact_native_execution(service, actual, backend)
        else:
            _assert_native_execution(service, actual, backend)

    structural = results[QueryType.STRUCTURAL]
    assert structural.discovered_entities == ("module:fem.materials",)

    dependency = results[QueryType.DEPENDENCY]
    assert {"module:fem.solver", "module:fem.materials"}.issubset(
        set(dependency.discovered_entities)
    )

    path = results[QueryType.PATH]
    assert evidence_target in path.discovered_entities
    assert path.evidence
    assert any(
        item.subject_id == "module:fem.materials"
        and item.predicate == "SUPPORTED_BY"
        and item.object_id == evidence_target
        for item in path.evidence
    )

    impact = results[QueryType.IMPACT]
    assert "file:tests/test_solver.py" in impact.metadata["affected_test_candidate_ids"]
    assert "file:.github/workflows/fem-validation.yml" in impact.metadata["affected_workflow_candidate_ids"]
    assert impact.metadata["cycle_analysis_status"] == "complete"
    assert impact.metadata["dependency_cycle_count"] == 1
    cycle = impact.metadata["dependency_cycles"][0]
    assert set(cycle["node_ids"]) == {"module:fem.mesh", "module:fem.solver"}
    assert graph.to_dict() == before
