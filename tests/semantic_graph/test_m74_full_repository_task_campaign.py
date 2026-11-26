"""Full-repository, source-derived M7.4 workload campaign.

This test intentionally builds the graph from the checked-out repository rather
than a synthetic graph or a small hand-maintained fixture. It is a bounded
integration workload, not a suitability verdict for every task/backend pair.
"""
from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path

import pytest

from audit_engine.semantic_audit.ae32b.evidence_tools import RepositoryEvidenceTools
from audit_engine.semantic_audit.graph.queries.models import GraphQuery, QueryType
from audit_engine.semantic_audit.graph.service import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.backend.snap_worker_adapter import SNAPWorkerProtocolError
from audit_engine.semantic_audit.graph.analysis import AnalysisStatus


BACKENDS = ("networkx", "scipy", "igraph", "graph-tool", "snap")
NATIVE_QUERY_MODES = {
    "networkx": "networkx_successor_predecessor_adjacency",
    "scipy": "scipy_csr_csc_adjacency",
    "igraph": "igraph_incident_edge_ids",
    "graph-tool": "graph_tool_vertex_edge_iterators",
    "snap": "snap_isolated_worker_tneanet_edge_ids",
}


def _require_selected_backend(backend: str) -> None:
    import os
    from importlib.util import find_spec

    selected = os.environ.get("AE32C_M74_BACKEND")
    if selected not in (None, backend):
        pytest.skip(f"workflow job targets {selected}, not {backend}")
    if backend == "snap":
        if not os.environ.get("AE32C_SNAP_WORKER_IMAGE"):
            pytest.skip("SNAP isolated worker image is not configured")
        if not os.environ.get("AE32C_SNAP_WORKER_IMAGE_ID"):
            pytest.skip("SNAP isolated worker image identity is not configured")
    elif backend == "graph-tool":
        if find_spec("graph_tool") is None:
            pytest.skip("graph-tool is not installed in this environment")
    elif backend == "igraph":
        if find_spec("igraph") is None:
            pytest.skip("python-igraph is not installed in this environment")
    elif backend == "scipy":
        if find_spec("scipy") is None:
            pytest.skip("SciPy is not installed in this environment")
    elif backend == "networkx":
        if find_spec("networkx") is None:
            pytest.skip("NetworkX is not installed in this environment")


def _select_module_chain(graph):
    modules = {
        node_id for edge in graph.edges
        for node_id in (edge.source_id, edge.target_id)
        if node_id.startswith("module:")
    }
    adjacency = defaultdict(set)
    for edge in graph.edges:
        if (
            edge.relation_type in {"IMPORTS", "DEPENDS_ON"}
            and edge.source_id in modules
            and edge.target_id in modules
        ):
            adjacency[edge.source_id].add(edge.target_id)

    for source in sorted(modules):
        queue = deque([(source, (source,))])
        visited = {source}
        while queue:
            current, path = queue.popleft()
            if len(path) >= 3:
                return source, path[-1], path
            if len(path) >= 5:
                continue
            for target in sorted(adjacency[current]):
                if target not in visited:
                    visited.add(target)
                    queue.append((target, (*path, target)))
    pytest.skip("full repository contains no bounded two-hop module dependency chain")


def _select_impact_source(graph):
    owners_by_file = defaultdict(set)
    for edge in graph.edges:
        if edge.relation_type == "IMPLEMENTED_BY" and edge.target_id.startswith("file:"):
            owners_by_file[edge.target_id].add(edge.source_id)

    test_modules = {
        edge.target_id
        for edge in graph.edges
        if edge.relation_type == "TESTS"
        and edge.source_id.startswith("file:tests/")
    }
    workflow_modules = {
        edge.target_id
        for edge in graph.edges
        if edge.relation_type == "INVOKES"
        and edge.source_id.startswith("file:.github/workflows/")
    }
    candidates = []
    for file_id, owners in owners_by_file.items():
        for owner in owners:
            if owner in test_modules:
                candidates.append((0, file_id, owner))
            elif owner in workflow_modules:
                candidates.append((1, file_id, owner))
    if not candidates:
        pytest.skip("full repository has no file/module ownership with test or workflow evidence")
    _, file_id, owner = sorted(candidates)[0]
    return file_id, owner


def _assert_same_semantics(actual, expected):
    assert actual.analysis_id == expected.analysis_id
    assert actual.query_id == expected.query_id
    assert actual.analysis_type == expected.analysis_type
    assert actual.status == expected.status
    assert actual.algorithm == expected.algorithm
    assert actual.graph_fingerprint == expected.graph_fingerprint
    assert actual.source_entities == expected.source_entities
    assert actual.discovered_entities == expected.discovered_entities
    assert actual.observations == expected.observations
    assert actual.evidence == expected.evidence
    assert actual.parameters == expected.parameters
    ignored = {"computation_backend"}
    actual_metadata = {
        key: value for key, value in actual.metadata.items()
        if not key.startswith("backend_") and key not in ignored
    }
    expected_metadata = {
        key: value for key, value in expected.metadata.items()
        if not key.startswith("backend_") and key not in ignored
    }
    assert actual_metadata == expected_metadata


@pytest.mark.parametrize("backend", BACKENDS)
def test_m74_full_repository_source_derived_task_campaign(backend):
    """Exercise all four public audit tasks on the actual checked-out repository graph."""
    _require_selected_backend(backend)
    repository_root = Path(__file__).resolve().parents[2]
    tools = RepositoryEvidenceTools(repository_root, graph_backend="reference")
    service = None
    try:
        graph = tools.graph
        before = graph.to_dict()
        assert len(graph.edges) > 0

        structural_edges = sorted(
            (
                edge for edge in graph.edges
                if edge.relation_type == "IMPORTS"
                and edge.source_id.startswith("module:")
                and edge.target_id.startswith("module:")
            ),
            key=lambda edge: (edge.source_id, edge.target_id),
        )
        if not structural_edges:
            pytest.skip("full repository has no source-derived module import edge")
        structural_source = structural_edges[0].source_id
        structural_target = structural_edges[0].target_id

        dependency_source, dependency_target, dependency_chain = _select_module_chain(graph)
        impact_source, impact_owner = _select_impact_source(graph)

        queries = (
            GraphQuery(
                "m74-full-repository-structural",
                QueryType.STRUCTURAL,
                (structural_source,),
                {"direction": "outgoing", "relation_types": ("IMPORTS",), "max_depth": 1},
            ),
            GraphQuery(
                "m74-full-repository-dependency",
                QueryType.DEPENDENCY,
                (dependency_source,),
                {
                    "direction": "outgoing",
                    "relation_types": ("IMPORTS", "DEPENDS_ON"),
                    "max_depth": 4,
                    "max_visited_nodes": 500,
                    "max_traversal_steps": 3000,
                },
            ),
            GraphQuery(
                "m74-full-repository-path",
                QueryType.PATH,
                (dependency_source,),
                {
                    "target_entity": dependency_target,
                    "direction": "outgoing",
                    "relation_types": ("IMPORTS", "DEPENDS_ON"),
                    "max_depth": 4,
                    "max_visited_nodes": 500,
                    "max_traversal_steps": 3000,
                },
            ),
            GraphQuery(
                "m74-full-repository-change-impact",
                QueryType.IMPACT,
                (impact_source,),
                {
                    "max_depth": 4,
                    "max_visited_nodes": 1000,
                    "max_traversal_steps": 5000,
                },
            ),
        )

        try:
            service = SemanticGraphAnalysisService(
                graph, traversal_backend=backend, verify_backend_parity=True,
            )
        except SNAPWorkerProtocolError as exc:
            if backend == "snap" and str(exc) == "snap_worker_request_exceeds_size_limit":
                pytest.skip(
                    "SNAP full-repository workload not executed: the isolated worker's "
                    "16 MiB JSON-lines initialization limit is below this graph payload; "
                    "this is a bounded transport limitation, not a suitability pass"
                )
            raise
        reference = SemanticGraphAnalysisService(
            graph, traversal_backend="reference", verify_backend_parity=True,
        )
        results = {}
        for query in queries:
            actual = service.analyze(query)
            expected = reference.analyze(query)
            _assert_same_semantics(actual, expected)
            assert actual.metadata["computation_backend"] == backend
            assert actual.metadata["backend_library"] == backend
            assert actual.metadata["backend_native_query_mode"] == NATIVE_QUERY_MODES[backend]
            assert actual.metadata["backend_parity_status"] == "verified_against_reference_per_query"
            metrics = actual.metadata["backend_native_query_metrics"]
            assert metrics["native_adjacency_lookups"] > 0
            assert metrics["native_edge_occurrences_read"] > 0
            results[query.query_type] = actual

        assert structural_target in results[QueryType.STRUCTURAL].discovered_entities
        assert dependency_target in results[QueryType.DEPENDENCY].discovered_entities
        path_result = results[QueryType.PATH]
        assert path_result.status is AnalysisStatus.COMPLETED
        assert dependency_target in path_result.discovered_entities

        impact = results[QueryType.IMPACT]
        assert impact.status in {AnalysisStatus.COMPLETED, AnalysisStatus.INCOMPLETE}
        assert impact.metadata["impact_direction"] == "incoming"
        assert impact.metadata["runtime_execution_proven"] is False
        assert impact.metadata["automatic_approval_permitted"] is False
        assert impact.metadata["authoritative_graph_mutation_permitted"] is False
        assert any(node_id.startswith("file:tests/") for node_id in impact.discovered_entities)
        if impact.status is AnalysisStatus.INCOMPLETE:
            assert (
                impact.metadata["truncated"] is True
                or impact.metadata["cycle_analysis_status"] != "complete"
            )

        runtime = service.engine.traversal_engine.runtime_report()["backend_execution"]
        assert runtime["queries_attempted"] >= len(queries)
        assert runtime["queries_succeeded"] == runtime["queries_attempted"]
        assert runtime["queries_failed"] == 0
        assert runtime["parity_verified_queries"] == runtime["queries_attempted"]
        assert runtime["parity_failures"] == 0
        assert runtime["native_adjacency_lookups"] > 0
        assert runtime["native_edge_occurrences_read"] > 0

        assert graph.to_dict() == before
        report = tools.graph_runtime_report()
        assert report["source_files_modified"] is False
        print({
            "backend": backend,
            "repository_files": len(tools.file_nodes),
            "graph_nodes": len(graph.nodes),
            "graph_edge_occurrences": len(graph.edges),
            "structural_source": structural_source,
            "structural_target": structural_target,
            "dependency_chain": list(dependency_chain),
            "impact_source": impact_source,
            "impact_owner": impact_owner,
            "impact_status": impact.status.value,
            "impact_candidates": len(impact.discovered_entities),
            "native_queries_attempted": runtime["queries_attempted"],
        })
    finally:
        if service is not None:
            close = getattr(service.engine.traversal_engine, "close", None)
            if callable(close):
                close()
        tools.close()
