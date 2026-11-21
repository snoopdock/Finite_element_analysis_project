"""NetworkX MultiDiGraph projection of the canonical semantic graph."""
from copy import deepcopy
from typing import Any

import networkx as nx

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph
from audit_engine.semantic_audit.graph.analysis.models import TraversalDirection
from audit_engine.semantic_audit.graph.backend.adapter_interface import (
    NativeEdgeOccurrence,
    NativeNodeRecord,
    SemanticGraphAdapter,
)

_EDGE_OCCURRENCE_KEY = "__ae32_semantic_edge_occurrence__"


class NetworkXAdapter(SemanticGraphAdapter):
    """Directed MultiDiGraph adapter with exact snapshot edge-occurrence IDs."""

    def __init__(self, graph: SemanticGraph):
        self.semantic_graph = graph
        self.graph = nx.MultiDiGraph()
        self._semantic_to_backend: dict[str, Any] = {}
        self._backend_to_semantic: dict[Any, str] = {}
        self._occurrence_to_backend: dict[int, tuple[Any, Any, Any]] = {}
        self._backend_to_occurrence: dict[tuple[Any, Any, Any], int] = {}
        self._build()

    def _build(self) -> None:
        for node in self.semantic_graph.nodes:
            backend_id = node.node_id
            self._semantic_to_backend[node.node_id] = backend_id
            self._backend_to_semantic[backend_id] = node.node_id
            self.graph.add_node(
                backend_id,
                entity_type=deepcopy(node.entity_type),
                attributes=deepcopy(node.attributes),
                metadata=deepcopy(node.metadata),
            )

        for occurrence, edge in enumerate(self.semantic_graph.edges):
            source = self._semantic_to_backend[edge.source_id]
            target = self._semantic_to_backend[edge.target_id]
            key = self.graph.add_edge(
                source,
                target,
                relation=deepcopy(edge.relation_type),
                attributes=deepcopy(edge.attributes),
                metadata=deepcopy(edge.metadata),
                **{_EDGE_OCCURRENCE_KEY: occurrence},
            )
            native_ref = (source, target, key)
            self._occurrence_to_backend[occurrence] = native_ref
            self._backend_to_occurrence[native_ref] = occurrence

    def export(self) -> nx.MultiDiGraph:
        return self.graph

    def backend_graph(self) -> nx.MultiDiGraph:
        return self.graph

    def nodes(self):
        return list(self.graph.nodes)

    def edges(self):
        return [
            {key: deepcopy(value) for key, value in data.items() if key != _EDGE_OCCURRENCE_KEY}
            for _, _, _, data in self.graph.edges(keys=True, data=True)
        ]

    def neighbors(self, node_id: str):
        if node_id not in self.graph:
            raise KeyError(node_id)
        return list(self.graph.successors(node_id))

    def capabilities(self) -> dict[str, Any]:
        return {
            "backend": "networkx",
            "package": "networkx",
            "native_graph_type": "MultiDiGraph",
            "directed": True,
            "directed_graph": True,
            "multiedges": True,
            "metadata": True,
            "native_parallel_edges": True,
            "native_self_loops": True,
            "native_node_attributes": True,
            "native_edge_attributes": True,
            "native_metadata": True,
            "semantic_edge_occurrence_identity": "reserved_native_edge_attribute",
            "native_adjacency_directions": ["outgoing", "incoming", "both"],
            "lossless": True,
            "acceptance_status": "not_established_by_capability_declaration",
        }

    def identity_mapping(self) -> dict[str, Any]:
        return {
            "semantic_to_backend": dict(self._semantic_to_backend),
            "backend_to_semantic": dict(self._backend_to_semantic),
            "semantic_edge_occurrence_to_backend": dict(self._occurrence_to_backend),
            "backend_to_semantic_edge_occurrence": dict(self._backend_to_occurrence),
        }

    def loss_report(self) -> dict[str, Any]:
        return {"lossless": True, "lost": [], "transformed": []}

    @staticmethod
    def _edge_record(source, target, key, data) -> NativeEdgeOccurrence:
        occurrence = data.get(_EDGE_OCCURRENCE_KEY)
        if type(occurrence) is not int or occurrence < 0:
            raise ValueError("networkx_edge_occurrence_mapping_invalid")
        return NativeEdgeOccurrence(
            occurrence_id=occurrence,
            source_id=source,
            target_id=target,
            relation_type=data["relation"],
            attributes=deepcopy(data["attributes"]),
            metadata=deepcopy(data["metadata"]),
            backend_edge_ref=(source, target, key),
        )

    def iter_native_nodes(self):
        for node_id, data in self.graph.nodes(data=True):
            yield NativeNodeRecord(
                node_id=node_id,
                entity_type=data["entity_type"],
                attributes=deepcopy(data["attributes"]),
                metadata=deepcopy(data["metadata"]),
            )

    def iter_native_edge_occurrences(self):
        for source, target, key, data in self.graph.edges(keys=True, data=True):
            yield self._edge_record(source, target, key, data)

    def iter_adjacent_edge_occurrences(self, node_id, direction):
        if node_id not in self.graph:
            raise KeyError(node_id)
        if isinstance(direction, str):
            direction = TraversalDirection(direction)
        if not isinstance(direction, TraversalDirection):
            raise ValueError(f"invalid traversal direction: {direction!r}")

        found: dict[int, NativeEdgeOccurrence] = {}
        if direction in (TraversalDirection.OUTGOING, TraversalDirection.BOTH):
            for neighbor, keyed in self.graph.succ[node_id].items():
                for key, data in keyed.items():
                    record = self._edge_record(node_id, neighbor, key, data)
                    found[record.occurrence_id] = record
        if direction in (TraversalDirection.INCOMING, TraversalDirection.BOTH):
            for neighbor, keyed in self.graph.pred[node_id].items():
                for key, data in keyed.items():
                    record = self._edge_record(neighbor, node_id, key, data)
                    found[record.occurrence_id] = record

        records = list(found.values())
        records.sort(
            key=lambda edge: (
                edge.target_id if edge.source_id == node_id else edge.source_id,
                edge.relation_type, edge.source_id, edge.target_id, edge.occurrence_id,
            )
        )
        return iter(records)
