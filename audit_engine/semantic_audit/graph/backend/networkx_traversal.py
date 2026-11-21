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
from audit_engine.semantic_audit.graph.analysis.models import TraversalDirection
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
from audit_engine.semantic_audit.graph.analysis.identity import edge_fingerprint, graph_fingerprint


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
            "native_adjacency_lookups": 0,
            "native_edge_occurrences_read": 0,
            "native_edge_occurrences_returned": 0,
            "native_edge_occurrences_validated": 0,
            "projection_validation_nodes": 0,
            "projection_validation_edge_occurrences": 0,
            "context_operation_telemetry": {},
        }
        self._context_reference_adjacency = None
        self._last_query_native_metrics = {
            "native_adjacency_lookups": 0,
            "native_edge_occurrences_read": 0,
        }
        self._verify_projection()

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
            existing_occurrence = data.get(_EDGE_OCCURRENCE_KEY)
            if existing_occurrence is not None and existing_occurrence != occurrence:
                raise BackendProjectionError("networkx_reserved_edge_key_collision")
            data[_EDGE_OCCURRENCE_KEY] = occurrence

    def _verify_projection(self) -> None:
        """Verify the complete native projection once before query execution.

        Query execution then uses NetworkX's indexed ``succ``/``pred``
        adjacency for only the nodes reached by the bounded traversal. The
        canonical edge tuple remains the semantic evidence side channel.
        """
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
        self._metrics["projection_validation_nodes"] = len(expected_nodes)

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

        if len(seen) != len(self._edge_occurrences):
            raise BackendProjectionError("networkx_projection_edge_count_mismatch")
        self._metrics["projection_validation_edge_occurrences"] = len(seen)

    def _build_adjacency(
        self,
    ) -> tuple[dict[str, list[SemanticEdge]], dict[str, list[SemanticEdge]]]:
        """Return no Python adjacency copy; traversal reads NetworkX per node."""
        if graph_fingerprint(self.graph) != self._source_fingerprint:
            raise BackendProjectionError("canonical_graph_changed_after_networkx_projection")
        return {}, {}

    def _validated_native_edge(
        self,
        source: str,
        target: str,
        data: dict[str, Any],
    ) -> SemanticEdge:
        occurrence = data.get(_EDGE_OCCURRENCE_KEY)
        if type(occurrence) is not int or not 0 <= occurrence < len(self._edge_occurrences):
            raise BackendProjectionError("networkx_edge_occurrence_mapping_invalid")
        edge = self._edge_occurrences[occurrence]
        if (
            edge.source_id != source
            or edge.target_id != target
            or data.get("relation") != edge.relation_type
            or data.get("attributes") != edge.attributes
            or data.get("metadata") != edge.metadata
        ):
            raise BackendProjectionError("networkx_projection_semantic_payload_mismatch")
        return edge

    def _candidate_edges(
        self,
        node_id: str,
        *,
        direction,
        relation_types: set[str] | None,
        outgoing: dict[str, list[SemanticEdge]],
        incoming: dict[str, list[SemanticEdge]],
    ) -> list[tuple[SemanticEdge, str]]:
        """Read only the selected node's native NetworkX adjacency entries."""
        if graph_fingerprint(self.graph) != self._source_fingerprint:
            raise BackendProjectionError("canonical_graph_changed_after_networkx_projection")
        if node_id not in self.native_graph:
            raise BackendProjectionError("networkx_projection_node_missing_during_query")
        canonical_node = self.graph.get_node(node_id)
        native_node = self.native_graph.nodes[node_id]
        if canonical_node is None or native_node != {
            "entity_type": canonical_node.entity_type,
            "attributes": canonical_node.attributes,
            "metadata": canonical_node.metadata,
        }:
            raise BackendProjectionError("networkx_projection_node_payload_mismatch")

        self._metrics["native_adjacency_lookups"] += 1
        candidates: list[tuple[SemanticEdge, str]] = []
        if direction in (TraversalDirection.OUTGOING, TraversalDirection.BOTH):
            for neighbor, keyed_edges in self.native_graph.succ[node_id].items():
                for data in keyed_edges.values():
                    self._metrics["native_edge_occurrences_read"] += 1
                    self._metrics["native_edge_occurrences_returned"] += 1
                    edge = self._validated_native_edge(node_id, neighbor, data)
                    self._metrics["native_edge_occurrences_validated"] += 1
                    if relation_types is None or edge.relation_type in relation_types:
                        candidates.append((edge, neighbor))
        if direction in (TraversalDirection.INCOMING, TraversalDirection.BOTH):
            for neighbor, keyed_edges in self.native_graph.pred[node_id].items():
                for data in keyed_edges.values():
                    # A BOTH expansion is a set of incident occurrences:
                    # a self-loop is already included by the outgoing index.
                    if direction is TraversalDirection.BOTH and neighbor == node_id:
                        continue
                    self._metrics["native_edge_occurrences_read"] += 1
                    self._metrics["native_edge_occurrences_returned"] += 1
                    edge = self._validated_native_edge(neighbor, node_id, data)
                    self._metrics["native_edge_occurrences_validated"] += 1
                    if relation_types is None or edge.relation_type in relation_types:
                        candidates.append((edge, neighbor))

        candidates.sort(
            key=lambda item: (
                item[1], item[0].relation_type, item[0].source_id,
                item[0].target_id, edge_fingerprint(item[0]),
            )
        )
        return candidates

    def context_edges(
        self,
        node_id: str,
        *,
        direction: TraversalDirection,
        relation_types: set[str] | None = None,
        operation: str,
    ) -> list[SemanticEdge]:
        """Return occurrence-preserving local adjacency for repository context tools.

        Callers retain their traversal order, depth limits, and evidence rendering
        while adjacency comes from NetworkX's keyed successor/predecessor indexes.
        """
        if not isinstance(operation, str) or not operation.strip():
            raise ValueError("context operation name must be non-empty")
        counters = self._metrics["context_operation_telemetry"].setdefault(
            operation,
            {
                "adjacency_queries_attempted": 0,
                "adjacency_queries_succeeded": 0,
                "adjacency_queries_failed": 0,
                "native_adjacency_lookups": 0,
                "native_edge_occurrences_read": 0,
                "parity_verified": 0,
                "parity_failures": 0,
            },
        )
        counters["adjacency_queries_attempted"] += 1
        native_before = {
            "native_adjacency_lookups": self._metrics["native_adjacency_lookups"],
            "native_edge_occurrences_read": self._metrics["native_edge_occurrences_read"],
        }
        try:
            if isinstance(direction, str):
                direction = TraversalDirection(direction)
            normalized = set(relation_types) if relation_types is not None else None
            native = self._candidate_edges(
                node_id, direction=direction, relation_types=normalized,
                outgoing={}, incoming={},
            )
            # Independently compare this exact local result with the reference
            # adjacency contract before returning it to a context tool.
            reference_engine = GraphTraversalEngine(self.graph)
            if self._context_reference_adjacency is None:
                self._context_reference_adjacency = reference_engine._build_adjacency()
            outgoing, incoming = self._context_reference_adjacency
            reference = reference_engine._candidate_edges(
                node_id, direction=direction, relation_types=normalized,
                outgoing=outgoing, incoming=incoming,
            )
            native_identity = [(edge_fingerprint(edge), neighbor) for edge, neighbor in native]
            reference_identity = [(edge_fingerprint(edge), neighbor) for edge, neighbor in reference]
            if native_identity != reference_identity:
                counters["parity_failures"] += 1
                raise BackendParityError("networkx_context_adjacency_parity_mismatch")
            counters["parity_verified"] += 1
            counters["adjacency_queries_succeeded"] += 1
            return [edge for edge, _neighbor in native]
        except Exception:
            counters["adjacency_queries_failed"] += 1
            raise
        finally:
            counters["native_adjacency_lookups"] += (
                self._metrics["native_adjacency_lookups"] - native_before["native_adjacency_lookups"]
            )
            counters["native_edge_occurrences_read"] += (
                self._metrics["native_edge_occurrences_read"] - native_before["native_edge_occurrences_read"]
            )

    def walk(self, *args: Any, **kwargs: Any) -> TraversalResult:
        self._metrics["queries_attempted"] += 1
        native_before = {
            "native_adjacency_lookups": self._metrics["native_adjacency_lookups"],
            "native_edge_occurrences_read": self._metrics["native_edge_occurrences_read"],
        }
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
            self._metrics["total_examined_edge_occurrences"] = (
                self._metrics.get("total_examined_edge_occurrences", 0) + result.examined_edges
            )
            self._metrics["total_visited_nodes"] += len(result.visited_nodes) + 1
            self._last_query_native_metrics = {
                key: self._metrics[key] - native_before[key] for key in native_before
            }
            return result
        except Exception:
            self._metrics["queries_failed"] += 1
            self._last_query_native_metrics = {
                key: self._metrics[key] - native_before[key] for key in native_before
            }
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
            "backend_native_query_mode": "networkx_successor_predecessor_adjacency",
            "backend_native_query_metrics": dict(self._last_query_native_metrics),
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
            "backend_native_query_mode": "networkx_successor_predecessor_adjacency",
            "backend_execution": dict(self._metrics),
            "context_operation_telemetry": {
                key: dict(value)
                for key, value in self._metrics["context_operation_telemetry"].items()
            },
        }
