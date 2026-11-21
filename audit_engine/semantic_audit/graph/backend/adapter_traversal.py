"""Deterministic traversal over non-NetworkX native graph adapters.

The selected native library supplies its own projection/adjacency representation.
AE-32 retains traversal ordering, bounds, evidence construction and semantic
interpretation. Every query is compared with the pure-Python reference engine.
"""
from __future__ import annotations

from collections import defaultdict
from importlib import metadata as importlib_metadata
from typing import Any

from audit_engine.semantic_audit.core.semantic_graph import (
    SemanticEdge, SemanticGraph, SemanticNode,
)
from audit_engine.semantic_audit.graph.analysis.identity import graph_fingerprint
from audit_engine.semantic_audit.graph.analysis.models import TraversalDirection
from audit_engine.semantic_audit.graph.analysis.traversal import (
    GraphTraversalEngine, TraversalResult,
)
from audit_engine.semantic_audit.graph.backend.backend_factory import BackendFactory
from audit_engine.semantic_audit.graph.backend.backend_pipeline import BackendPipeline
from audit_engine.semantic_audit.graph.backend.backend_selector import BackendSelectionPolicy
from audit_engine.semantic_audit.graph.backend.capability_registry import create_default_registry
from audit_engine.semantic_audit.graph.backend.execution_context import BackendExecutionContext
from audit_engine.semantic_audit.graph.backend.optional_backend_support import (
    BackendUnavailableError, make_projection,
)


class NativeAdapterProjectionError(RuntimeError):
    """A native projection no longer matches its canonical SemanticGraph."""


class NativeAdapterParityError(RuntimeError):
    """A native adapter traversal disagreed with the reference traversal."""


_DISTRIBUTIONS = {
    "scipy": "scipy",
    "igraph": "igraph",
    "graph-tool": "graph-tool",
    "snap": "snap-stanford",
}
_PROJECTION_TYPES = {
    "scipy": "scipy.sparse.csr_matrix",
    "igraph": "igraph.Graph",
    "graph-tool": "graph_tool.Graph",
    "snap": "snap.TNEANet",
}


def _clone_validated_graph(graph: SemanticGraph) -> SemanticGraph:
    projection = make_projection(graph)
    nodes = [
        SemanticNode(item["id"], item["type"], item["attributes"], item["metadata"])
        for item in projection.nodes
    ]
    edges = [
        SemanticEdge(
            item["source"], item["target"], item["relation"],
            item["attributes"], item["metadata"],
        )
        for item in projection.edges
    ]
    return SemanticGraph(nodes=nodes, edges=edges)


def _library_version(name: str, adapter: Any) -> str | None:
    try:
        return importlib_metadata.version(_DISTRIBUTIONS[name])
    except importlib_metadata.PackageNotFoundError:
        module = {
            "scipy": "scipy",
            "igraph": "igraph",
            "graph-tool": "graph_tool",
            "snap": "snap",
        }[name]
        imported = __import__(module)
        value = getattr(imported, "__version__", None)
        return str(value) if value is not None else None


class NativeAdapterGraphTraversalEngine(GraphTraversalEngine):
    """Use an explicitly selected native adapter for semantic graph queries."""

    SUPPORTED_BACKENDS = frozenset({"scipy", "igraph", "graph-tool", "snap"})

    def __init__(
        self,
        graph: SemanticGraph,
        backend_name: str,
        *,
        verify_parity: bool = True,
    ) -> None:
        if backend_name not in self.SUPPORTED_BACKENDS:
            raise ValueError(f"Unsupported native adapter traversal backend: {backend_name!r}")
        super().__init__(graph)
        self._backend_name = backend_name
        self.verify_parity = bool(verify_parity)
        self._source_fingerprint = graph_fingerprint(graph)
        projection_graph = _clone_validated_graph(graph)

        registry = create_default_registry()
        capabilities = registry.get(backend_name)["capabilities"]
        if not capabilities.get("available", False):
            raise BackendUnavailableError(
                f"Graph backend {backend_name!r} is not installed or discoverable."
            )
        if not capabilities.get("semantic_traversal", False):
            raise BackendUnavailableError(
                f"Graph backend {backend_name!r} is not approved for semantic traversal."
            )

        pipeline = BackendPipeline(BackendSelectionPolicy(registry), BackendFactory())
        self.backend_execution = pipeline.execute(
            {"available": True, "semantic_traversal": True},
            BackendExecutionContext(
                projection_graph,
                task_type="ae32b_semantic_traversal",
                preserve_metadata=True,
                provenance_tracking=True,
                validation_mode=True,
            ),
            preferred_backend=backend_name,
        )
        self.adapter = self.backend_execution.output
        self.native_graph = self.adapter.export()
        self._edge_occurrences = tuple(graph.edges)
        self._projection_validated = False
        self._projection_node_count = 0
        self._projection_edge_occurrence_count = 0
        self._last_query_native_metrics = {
            "native_adjacency_lookups": 0,
            "native_edge_occurrences_read": 0,
        }
        self._metrics = {
            "queries_attempted": 0,
            "queries_succeeded": 0,
            "queries_failed": 0,
            "parity_verified_queries": 0,
            "parity_failures": 0,
            "total_examined_edges": 0,
            "total_visited_nodes": 0,
            "native_projection_reads": 0,
            "native_adjacency_lookups": 0,
            "native_edge_occurrences_read": 0,
        }
        # Fail during construction if the native projection is already corrupt.
        self._build_adjacency()

    @property
    def backend_name(self) -> str:
        return self._backend_name

    def _build_adjacency(self):
        if graph_fingerprint(self.graph) != self._source_fingerprint:
            raise NativeAdapterProjectionError("canonical_graph_changed_after_native_projection")
        # SciPy's complete projection is validated once at construction.
        # Every subsequent walk receives empty Python indexes and must obtain
        # candidates from CSR/CSC local adjacency.
        if self._backend_name in {"scipy", "igraph"} and self._projection_validated:
            return {}, {}

        expected_nodes = {
            node.node_id: {
                "id": node.node_id,
                "type": node.entity_type,
                "attributes": node.attributes,
                "metadata": node.metadata,
            }
            for node in self.graph.nodes
        }
        native_nodes = list(self.adapter.iter_native_nodes())
        observed_nodes = {}
        for item in native_nodes:
            if not isinstance(item, dict):
                raise NativeAdapterProjectionError("native_node_payload_invalid")
            ident = item.get("id")
            if not isinstance(ident, str) or ident in observed_nodes:
                raise NativeAdapterProjectionError("native_node_identity_invalid_or_duplicate")
            observed_nodes[ident] = item
        if observed_nodes != expected_nodes:
            raise NativeAdapterProjectionError("native_node_projection_semantic_mismatch")

        outgoing = defaultdict(list)
        incoming = defaultdict(list)
        seen: set[int] = set()
        native_edges = list(self.adapter.iter_native_edges())
        self._metrics["native_projection_reads"] += len(native_nodes) + len(native_edges)

        for item in native_edges:
            if not isinstance(item, dict):
                raise NativeAdapterProjectionError("native_edge_payload_invalid")
            occurrence = item.get("occurrence")
            if type(occurrence) is not int or not 0 <= occurrence < len(self._edge_occurrences):
                raise NativeAdapterProjectionError("native_edge_occurrence_invalid")
            if occurrence in seen:
                raise NativeAdapterProjectionError("native_edge_occurrence_duplicate")
            seen.add(occurrence)
            edge = self._edge_occurrences[occurrence]
            if (
                item.get("source") != edge.source_id
                or item.get("target") != edge.target_id
                or item.get("relation") != edge.relation_type
                or item.get("attributes") != edge.attributes
                or item.get("metadata") != edge.metadata
            ):
                raise NativeAdapterProjectionError("native_edge_projection_semantic_mismatch")
            outgoing[edge.source_id].append(edge)
            incoming[edge.target_id].append(edge)

        if len(seen) != len(self._edge_occurrences):
            raise NativeAdapterProjectionError("native_edge_projection_occurrence_count_mismatch")
        if graph_fingerprint(self.graph) != self._source_fingerprint:
            raise NativeAdapterProjectionError("canonical_graph_changed_during_native_projection_read")
        self._projection_node_count = len(native_nodes)
        self._projection_edge_occurrence_count = len(seen)
        if self._backend_name in {"scipy", "igraph"}:
            self._projection_validated = True
        return dict(outgoing), dict(incoming)

    def _candidate_edges(
        self,
        node_id: str,
        *,
        direction,
        relation_types: set[str] | None,
        outgoing: dict[str, list[SemanticEdge]],
        incoming: dict[str, list[SemanticEdge]],
    ):
        if self._backend_name not in {"scipy", "igraph"}:
            return super()._candidate_edges(
                node_id, direction=direction, relation_types=relation_types,
                outgoing=outgoing, incoming=incoming,
            )
        if isinstance(direction, str):
            direction = TraversalDirection(direction)
        self._metrics["native_adjacency_lookups"] += 1
        try:
            records = self.adapter.iter_adjacent_edge_occurrences(node_id, direction)
        except ValueError as exc:
            raise NativeAdapterProjectionError(str(exc)) from exc
        self._metrics["native_edge_occurrences_read"] += len(records)
        candidates = []
        seen = set()
        for record in records:
            occurrence = record.occurrence_id
            if type(occurrence) is not int or not 0 <= occurrence < len(self._edge_occurrences):
                raise NativeAdapterProjectionError(f"{self._backend_name}_native_edge_occurrence_invalid")
            if occurrence in seen:
                raise NativeAdapterProjectionError(f"{self._backend_name}_native_edge_occurrence_duplicate")
            seen.add(occurrence)
            edge = self._edge_occurrences[occurrence]
            if (
                record.source_id != edge.source_id
                or record.target_id != edge.target_id
                or record.relation_type != edge.relation_type
                or record.attributes != edge.attributes
                or record.metadata != edge.metadata
            ):
                raise NativeAdapterProjectionError(f"{self._backend_name}_native_edge_occurrence_semantic_mismatch")
            if relation_types is not None and edge.relation_type not in relation_types:
                continue
            neighbor = edge.target_id if edge.source_id == node_id else edge.source_id
            candidates.append((edge, neighbor))
        candidates.sort(key=lambda item: (
            item[1], item[0].relation_type, item[0].source_id, item[0].target_id,
        ))
        return candidates

    def walk(self, *args: Any, **kwargs: Any) -> TraversalResult:
        self._metrics["queries_attempted"] += 1
        native_lookups_before = self._metrics["native_adjacency_lookups"]
        native_occurrences_before = self._metrics["native_edge_occurrences_read"]
        try:
            if graph_fingerprint(self.graph) != self._source_fingerprint:
                raise NativeAdapterProjectionError("canonical_graph_changed_before_native_query")
            result = super().walk(*args, **kwargs)
            if graph_fingerprint(self.graph) != self._source_fingerprint:
                raise NativeAdapterProjectionError("canonical_graph_changed_during_native_query")
            if self.verify_parity:
                reference = GraphTraversalEngine(self.graph).walk(*args, **kwargs)
                if graph_fingerprint(self.graph) != self._source_fingerprint:
                    raise NativeAdapterProjectionError("canonical_graph_changed_during_reference_check")
                if result != reference:
                    self._metrics["parity_failures"] += 1
                    raise NativeAdapterParityError(
                        f"{self._backend_name}_reference_traversal_parity_mismatch"
                    )
                self._metrics["parity_verified_queries"] += 1
            self._last_query_native_metrics = {
                "native_adjacency_lookups": (
                    self._metrics["native_adjacency_lookups"] - native_lookups_before
                ),
                "native_edge_occurrences_read": (
                    self._metrics["native_edge_occurrences_read"] - native_occurrences_before
                ),
            }
            self._metrics["queries_succeeded"] += 1
            self._metrics["total_examined_edges"] += result.examined_edges
            self._metrics["total_visited_nodes"] += len(result.visited_nodes) + 1
            return result
        except Exception:
            self._metrics["queries_failed"] += 1
            raise

    def result_metadata(self) -> dict:
        metadata = {
            "computation_backend": self._backend_name,
            "computation_algorithm": self.ALGORITHM,
            "backend_library": self._backend_name,
            "backend_library_version": _library_version(self._backend_name, self.adapter),
            "backend_projection_type": _PROJECTION_TYPES[self._backend_name],
            "backend_parity_status": (
                "verified_against_reference_per_query"
                if self.verify_parity else "not_checked"
            ),
            "backend_projection_fingerprint": self._source_fingerprint,
            "backend_loss_assessment": self.backend_execution.loss_assessment.to_dict(),
            "backend_semantic_query_preservation": (
                "exact_via_canonical_edge_side_channels"
                if self._backend_name == "scipy"
                else "native_projection_verified_against_canonical_semantic_graph"
            ),
        }
        if self._backend_name in {"scipy", "igraph"}:
            metadata["backend_native_query_mode"] = (
                "scipy_csr_csc_adjacency" if self._backend_name == "scipy"
                else "igraph_incident_edge_ids"
            )
            metadata["backend_native_query_metrics"] = dict(self._last_query_native_metrics)
        return metadata

    def runtime_report(self) -> dict:
        return {
            "active_computation_backend": self._backend_name,
            "active_traversal_algorithm": self.ALGORITHM,
            "backend_library": self._backend_name,
            "backend_library_version": _library_version(self._backend_name, self.adapter),
            "backend_projection_type": _PROJECTION_TYPES[self._backend_name],
            "backend_projection_fingerprint": self._source_fingerprint,
            "backend_native_query_mode": (
                "scipy_csr_csc_adjacency" if self._backend_name == "scipy"
                else "igraph_incident_edge_ids" if self._backend_name == "igraph"
                else "canonical_python_adjacency_fallback"
            ),
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
            "backend_loss_assessment": self.backend_execution.loss_assessment.to_dict(),
            "backend_semantic_query_preservation": (
                "exact_via_canonical_edge_side_channels"
                if self._backend_name == "scipy"
                else "native_projection_verified_against_canonical_semantic_graph"
            ),
            "projection_node_count": (
                self._projection_node_count if self._backend_name in {"scipy", "igraph"}
                else len(list(self.adapter.iter_native_nodes()))
            ),
            "projection_edge_occurrence_count": (
                self._projection_edge_occurrence_count if self._backend_name in {"scipy", "igraph"}
                else len(list(self.adapter.iter_native_edges()))
            ),
            "native_adjacency": (
                self.adapter.native_adjacency_report()
                if self._backend_name in {"scipy", "igraph"} else None
            ),
            "backend_execution": dict(self._metrics),
        }
