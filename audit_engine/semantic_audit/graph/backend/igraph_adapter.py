"""Native python-igraph projection with exact local edge-occurrence access."""
from copy import deepcopy

from audit_engine.semantic_audit.graph.analysis.models import TraversalDirection
from audit_engine.semantic_audit.graph.backend.adapter_interface import (
    NativeEdgeOccurrence, SemanticGraphAdapter,
)
from audit_engine.semantic_audit.graph.backend.optional_backend_support import (
    NativeAdapterMixin, make_projection, require_backend,
)


class IGraphAdapter(NativeAdapterMixin, SemanticGraphAdapter):
    backend_name = "igraph"

    def __init__(self, graph):
        ig = require_backend("igraph")
        data = make_projection(graph)
        native = ig.Graph(directed=True)
        native.add_vertices(len(data.nodes))
        if data.nodes:
            native.vs["semantic_id"] = [n["id"] for n in data.nodes]
            native.vs["entity_type"] = [n["type"] for n in data.nodes]
            native.vs["attributes"] = [n["attributes"] for n in data.nodes]
            native.vs["metadata"] = [n["metadata"] for n in data.nodes]
        if data.edges:
            native.add_edges([(e["source_index"], e["target_index"]) for e in data.edges])
            native.es["relation"] = [e["relation"] for e in data.edges]
            native.es["attributes"] = [e["attributes"] for e in data.edges]
            native.es["metadata"] = [e["metadata"] for e in data.edges]
            native.es["semantic_occurrence"] = [e["occurrence"] for e in data.edges]
        self.semantic_graph = graph
        self._projection = data
        self._index = dict(data.node_to_index)
        self._edge_ids = {e["occurrence"]: e["occurrence"] for e in data.edges}
        self.graph = native
        self._adjacency_metrics = {
            "native_adjacency_lookups": 0,
            "outgoing_incident_edge_lookups": 0,
            "incoming_incident_edge_lookups": 0,
            "native_edge_occurrences_read": 0,
        }

    def iter_native_nodes(self):
        for vertex in self.graph.vs:
            yield {
                "id": vertex["semantic_id"],
                "type": vertex["entity_type"],
                "attributes": vertex["attributes"],
                "metadata": vertex["metadata"],
            }

    def iter_native_edges(self):
        for edge in self.graph.es:
            source_vertex = self.graph.vs[edge.source]
            target_vertex = self.graph.vs[edge.target]
            yield {
                "occurrence": int(edge["semantic_occurrence"]),
                "source": source_vertex["semantic_id"],
                "target": target_vertex["semantic_id"],
                "relation": edge["relation"],
                "attributes": edge["attributes"],
                "metadata": edge["metadata"],
            }

    def iter_adjacent_edge_occurrences(self, node_id, direction):
        """Read incident edge IDs for one vertex; never enumerate the full graph."""
        if node_id not in self._index:
            raise KeyError(node_id)
        if isinstance(direction, str):
            direction = TraversalDirection(direction)
        if not isinstance(direction, TraversalDirection):
            raise ValueError("igraph_adjacency_direction_invalid")

        vertex_id = self._index[node_id]
        edge_ids = set()
        self._adjacency_metrics["native_adjacency_lookups"] += 1
        if direction in (TraversalDirection.OUTGOING, TraversalDirection.BOTH):
            self._adjacency_metrics["outgoing_incident_edge_lookups"] += 1
            edge_ids.update(self.graph.incident(vertex_id, mode="out"))
        if direction in (TraversalDirection.INCOMING, TraversalDirection.BOTH):
            self._adjacency_metrics["incoming_incident_edge_lookups"] += 1
            edge_ids.update(self.graph.incident(vertex_id, mode="in"))

        records = []
        for edge_id in sorted(edge_ids):
            if type(edge_id) is not int or not 0 <= edge_id < self.graph.ecount():
                raise ValueError("igraph_native_edge_id_invalid")
            edge = self.graph.es[edge_id]
            occurrence = edge["semantic_occurrence"]
            if type(occurrence) is not int or occurrence != self._edge_ids.get(occurrence):
                raise ValueError("igraph_semantic_occurrence_mapping_invalid")
            source = self.graph.vs[edge.source]["semantic_id"]
            target = self.graph.vs[edge.target]["semantic_id"]
            canonical = self._projection.edges[occurrence]
            if (
                source != canonical["source"]
                or target != canonical["target"]
                or edge["relation"] != canonical["relation"]
                or edge["attributes"] != canonical["attributes"]
                or edge["metadata"] != canonical["metadata"]
            ):
                raise ValueError("igraph_native_edge_occurrence_semantic_mismatch")
            records.append(NativeEdgeOccurrence(
                occurrence_id=occurrence,
                source_id=source,
                target_id=target,
                relation_type=edge["relation"],
                attributes=deepcopy(edge["attributes"]),
                metadata=deepcopy(edge["metadata"]),
                backend_edge_ref=("igraph", edge_id, occurrence),
            ))
        self._adjacency_metrics["native_edge_occurrences_read"] += len(records)
        return tuple(records)

    def native_adjacency_report(self):
        return dict(self._adjacency_metrics)
