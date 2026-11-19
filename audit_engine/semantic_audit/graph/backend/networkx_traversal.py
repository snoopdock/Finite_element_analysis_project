"""NetworkX-backed traversal for the canonical semantic graph.

NetworkX supplies the indexed directed multigraph projection. AE-32 keeps
control of deterministic BFS ordering, bounds, evidence construction and
semantic interpretation. Every query is shadow-checked against the pure
Python reference traversal before its result is accepted.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import networkx as nx

from audit_engine.semantic_audit.core.semantic_graph import (
    SemanticEdge,
    SemanticGraph,
    SemanticNode,
)
from audit_engine.semantic_audit.graph.analysis.traversal import (
    GraphTraversalEngine,
    TraversalResult,
)
from audit_engine.semantic_audit.graph.backend.backend_factory import BackendFactory
from audit_engine.semantic_audit.graph.backend.backend_pipeline import BackendPipeline
from audit_engine.semantic_audit.graph.backend.backend_selector import BackendSelectionPolicy
from audit_engine.semantic_audit.graph.backend.capability_registry import create_default_registry
from audit_engine.semantic_audit.graph.backend.execution_context import BackendExecutionContext
from audit_engine.semantic_audit.graph.backend.optional_backend_support import (
    BackendUnavailableError,
    make_projection,
)
from audit_engine.semantic_audit.graph.analysis.identity import graph_fingerprint


_EDGE_OCCURRENCE_KEY = "__ae32_semantic_edge_occurrence__"
_REQUIRED_CAPABILITIES = {
    "available": True,
    "directed": True,
    "multiedges": True,
    "metadata": True,
    "lossless": True,
}


class BackendProjectionError(RuntimeError):
    """The native graph projection no longer matches the canonical snapshot."""


class BackendParityError(RuntimeError):
    """The external backend disagreed with the deterministic reference result."""


def _clone_validated_graph(graph: SemanticGraph) -> SemanticGraph:
    """Create an isolated canonical copy from the validated projection payload."""
    projection = make_projection(graph)
    nodes = [
        SemanticNode(
            node_id=item["id"],
            entity_type=item["type"],
            attributes=item["attributes"],
            metadata=item["metadata"],
        )
        for item in projection.nodes
    ]
    edges = [
        SemanticEdge(
            source_id=item["source"],
            target_id=item["target"],
            relation_type=item["relation"],
            attributes=item["attributes"],
            metadata=item["metadata"],
        )
        for item in projection.edges
    ]
    return SemanticGraph(nodes=nodes, edges=edges)


class NetworkXGraphTraversalEngine(GraphTraversalEngine):
    """Deterministic traversal over a NetworkX MultiDiGraph projection.

    The reference engine remains the correctness oracle. `verify_parity=True`
    is the production default: no NetworkX result is returned unless the full
    TraversalResult (including ordered steps, evidence and truncation) matches
    the reference implementation exactly.
    """

    def __init__(self, graph: SemanticGraph, *, verify_parity: bool = True) -> None:
        super().__init__(graph)
        self.verify_parity = bool(verify_parity)
        self._source_fingerprint = graph_fingerprint(graph)
        projection_graph = _clone_validated_graph(graph)

        registry = create_default_registry()
        networkx_caps = registry.get("networkx")["capabilities"]
        if not networkx_caps.get("available", False):
            raise BackendUnavailableError(
                "NetworkX is required for the AE-32B graph query backend. "
                "Install the repository's declared networkx dependency."
            )
        pipeline = BackendPipeline(BackendSelectionPolicy(registry), BackendFactory())
        self.backend_execution = pipeline.execute(
            _REQUIRED_CAPABILITIES,
            BackendExecutionContext(
                projection_graph,
                task_type="ae32b_semantic_traversal",
                preserve_metadata=True,
                provenance_tracking=True,
                validation_mode=True,
            ),
        )
        if self.backend_execution.backend != "networkx":
            raise BackendUnavailableError(
                "The selected backend does not satisfy the NetworkX traversal implementation."
            )
        self.adapter = self.backend_execution.output
        self.native_graph = self.adapter.export()
        self._edge_occurrences = tuple(graph.edges)
        self._attach_edge_occurrence_ids()
        self._metrics = {
            "queries_attempted": 0,
            "queries_succeeded": 0,
            "queries_failed": 0,
            "parity_verified_queries": 0,
            "parity_failures": 0,
            "total_examined_edges": 0,
            "total_visited_nodes": 0,
        }

    @property
    def backend_name(self) -> str:
        return "networkx"

    def _attach_edge_occurrence_ids(self) -> None:
        """Bind each MultiDiGraph edge key to its canonical edge occurrence."""
        pair_keys: dict[tuple[str, str], int] = defaultdict(int)
        for occurrence, edge in enumerate(self._edge_occurrences):
            pair = (edge.source_id, edge.target_id)
            key = pair_keys[pair]
            pair_keys[pair] += 1
            data = self.native_graph.get_edge_data(pair[0], pair[1], key)
            if not isinstance(data, dict):
                raise BackendProjectionError("networkx_projection_edge_missing")
            if _EDGE_OCCURRENCE_KEY in data:
                raise BackendProjectionError("networkx_reserved_edge_key_collision")
            data[_EDGE_OCCURRENCE_KEY] = occurrence

    def _build_adjacency(
        self,
    ) -> tuple[dict[str, list[SemanticEdge]], dict[str, list[SemanticEdge]]]:
        """Read edge occurrences from NetworkX's directed multigraph index."""
        if graph_fingerprint(self.graph) != self._source_fingerprint:
            raise BackendProjectionError("canonical_graph_changed_after_networkx_projection")

        expected_nodes = {node.node_id for node in self.graph.nodes}
        if set(self.native_graph.nodes) != expected_nodes:
            raise BackendProjectionError("networkx_projection_node_identity_mismatch")
        for node in self.graph.nodes:
            native_data = self.native_graph.nodes[node.node_id]
            if native_data != {
                "entity_type": node.entity_type,
                "attributes": node.attributes,
                "metadata": node.metadata,
            }:
                raise BackendProjectionError("networkx_projection_node_payload_mismatch")

        outgoing: dict[str, list[SemanticEdge]] = {}
        incoming: dict[str, list[SemanticEdge]] = {}
        seen: set[int] = set()

        for source, target, _key, data in self.native_graph.edges(keys=True, data=True):
            occurrence = data.get(_EDGE_OCCURRENCE_KEY)
            if type(occurrence) is not int or not 0 <= occurrence < len(self._edge_occurrences):
                raise BackendProjectionError("networkx_edge_occurrence_mapping_invalid")
            if occurrence in seen:
                raise BackendProjectionError("networkx_edge_occurrence_mapping_duplicate")
            seen.add(occurrence)
            edge = self._edge_occurrences[occurrence]
            if (
                edge.source_id != source
                or edge.target_id != target
                or data.get("relation") != edge.relation_type
                or data.get("attributes") != edge.attributes
                or data.get("metadata") != edge.metadata
            ):
                raise BackendProjectionError("networkx_projection_semantic_payload_mismatch")
            outgoing.setdefault(source, []).append(edge)
            incoming.setdefault(target, []).append(edge)

        if len(seen) != len(self._edge_occurrences):
            raise BackendProjectionError("networkx_projection_edge_count_mismatch")
        return outgoing, incoming

    def walk(self, *args: Any, **kwargs: Any) -> TraversalResult:
        self._metrics["queries_attempted"] += 1
        try:
            if graph_fingerprint(self.graph) != self._source_fingerprint:
                raise BackendProjectionError("canonical_graph_changed_after_networkx_projection")
            result = super().walk(*args, **kwargs)
            if graph_fingerprint(self.graph) != self._source_fingerprint:
                raise BackendProjectionError("canonical_graph_changed_during_networkx_query")
            if self.verify_parity:
                reference = GraphTraversalEngine(self.graph).walk(*args, **kwargs)
                if graph_fingerprint(self.graph) != self._source_fingerprint:
                    raise BackendProjectionError("canonical_graph_changed_during_reference_parity_check")
                if result != reference:
                    self._metrics["parity_failures"] += 1
                    raise BackendParityError("networkx_reference_traversal_parity_mismatch")
                self._metrics["parity_verified_queries"] += 1
            self._metrics["queries_succeeded"] += 1
            self._metrics["total_examined_edges"] += result.examined_edges
            self._metrics["total_visited_nodes"] += len(result.visited_nodes) + 1
            return result
        except Exception:
            self._metrics["queries_failed"] += 1
            raise

    def result_metadata(self) -> dict:
        return {
            "computation_backend": "networkx",
            "computation_algorithm": self.ALGORITHM,
            "backend_library": "networkx",
            "backend_library_version": nx.__version__,
            "backend_projection_type": "MultiDiGraph",
            "backend_parity_status": (
                "verified_against_reference_per_query"
                if self.verify_parity else "not_checked"
            ),
            "backend_projection_fingerprint": self._source_fingerprint,
        }

    def runtime_report(self) -> dict:
        return {
            "active_computation_backend": "networkx",
            "active_traversal_algorithm": self.ALGORITHM,
            "backend_library": "networkx",
            "backend_library_version": nx.__version__,
            "backend_projection_type": "MultiDiGraph",
            "backend_projection_fingerprint": self._source_fingerprint,
            "backend_parity_mode": (
                "strict_per_query_reference_comparison"
                if self.verify_parity else "disabled"
            ),
            "backend_pipeline": self.backend_execution.summary(),
            "backend_pipeline_provenance": [
                item.to_dict() for item in self.backend_execution.provenance_records
            ],
            "backend_pipeline_transformations": [
                item.to_dict() for item in self.backend_execution.transformation_records
            ],
            "projection_node_count": self.native_graph.number_of_nodes(),
            "projection_edge_occurrence_count": self.native_graph.number_of_edges(),
            "backend_execution": dict(self._metrics),
        }
