"""Native graph-tool projection with exact local edge-occurrence access.

Object-valued property maps are intended for in-process computation; they are
not claimed to survive graph-tool's binary/XML serialization.
"""
from copy import deepcopy

from audit_engine.semantic_audit.graph.analysis.models import TraversalDirection
from audit_engine.semantic_audit.graph.backend.adapter_interface import (
    NativeEdgeOccurrence, SemanticGraphAdapter,
)
from audit_engine.semantic_audit.graph.backend.optional_backend_support import (
    NativeAdapterMixin, make_projection, require_backend,
)


class GraphToolAdapter(NativeAdapterMixin, SemanticGraphAdapter):
    backend_name = "graph-tool"

    def __init__(self, graph):
        gt = require_backend("graph-tool")
        data = make_projection(graph)
        native = gt.Graph(directed=True)
        native.add_vertex(len(data.nodes))
        node_props = {
            "semantic_id": native.new_vertex_property("string"),
            "entity_type": native.new_vertex_property("string"),
            "attributes": native.new_vertex_property("object"),
            "metadata": native.new_vertex_property("object"),
        }
        edge_props = {
            "relation": native.new_edge_property("string"),
            "attributes": native.new_edge_property("object"),
            "metadata": native.new_edge_property("object"),
            "semantic_occurrence": native.new_edge_property("int64_t"),
        }
        for key, prop in node_props.items():
            native.vertex_properties[key] = prop
        for key, prop in edge_props.items():
            native.edge_properties[key] = prop
        for i, node in enumerate(data.nodes):
            vertex = native.vertex(i)
            for prop_name, field in (
                ("semantic_id", "id"), ("entity_type", "type"),
                ("attributes", "attributes"), ("metadata", "metadata"),
            ):
                node_props[prop_name][vertex] = deepcopy(node[field])
        native_edge_id_to_occurrence = {}
        for edge in data.edges:
            native_edge = native.add_edge(
                native.vertex(edge["source_index"]),
                native.vertex(edge["target_index"]),
            )
            for prop_name, field in (
                ("relation", "relation"), ("attributes", "attributes"),
                ("metadata", "metadata"), ("semantic_occurrence", "occurrence"),
            ):
                edge_props[prop_name][native_edge] = deepcopy(edge[field])
            native_edge_id = int(native.edge_index[native_edge])
            if native_edge_id in native_edge_id_to_occurrence:
                raise ValueError("graph_tool_native_edge_index_duplicate")
            native_edge_id_to_occurrence[native_edge_id] = edge["occurrence"]

        self.semantic_graph = graph
        self._projection = data
        self._index = dict(data.node_to_index)
        self._edge_ids = {e["occurrence"]: e["occurrence"] for e in data.edges}
        self._native_edge_id_to_occurrence = native_edge_id_to_occurrence
        self.graph = native
        self._adjacency_metrics = {
            "native_adjacency_lookups": 0,
            "outgoing_edge_iterator_lookups": 0,
            "incoming_edge_iterator_lookups": 0,
            "native_edge_occurrences_read": 0,
        }

    def loss_report(self):
        report = super().loss_report()
        report["scope"] = (
            "in_memory_only; Python-object property maps are not portable "
            "graph-tool binary/XML serialization"
        )
        return report

    def iter_native_nodes(self):
        props = self.graph.vertex_properties
        for vertex in self.graph.vertices():
            yield {
                "id": props["semantic_id"][vertex],
                "type": props["entity_type"][vertex],
                "attributes": props["attributes"][vertex],
                "metadata": props["metadata"][vertex],
            }

    def iter_native_edges(self):
        vp = self.graph.vertex_properties
        ep = self.graph.edge_properties
        for edge in self.graph.edges():
            yield {
                "occurrence": int(ep["semantic_occurrence"][edge]),
                "source": vp["semantic_id"][edge.source()],
                "target": vp["semantic_id"][edge.target()],
                "relation": ep["relation"][edge],
                "attributes": ep["attributes"][edge],
                "metadata": ep["metadata"][edge],
            }

    def iter_adjacent_edge_occurrences(self, node_id, direction):
        """Read only this vertex's native incoming/outgoing edge iterators."""
        if node_id not in self._index:
            raise KeyError(node_id)
        if isinstance(direction, str):
            direction = TraversalDirection(direction)
        if not isinstance(direction, TraversalDirection):
            raise ValueError("graph_tool_adjacency_direction_invalid")

        vertex = self.graph.vertex(self._index[node_id])
        selected = {}
        self._adjacency_metrics["native_adjacency_lookups"] += 1

        def collect(edges):
            for edge in edges:
                native_edge_id = int(self.graph.edge_index[edge])
                occurrence = self._native_edge_id_to_occurrence.get(native_edge_id)
                if type(occurrence) is not int or self._edge_ids.get(occurrence) != occurrence:
                    raise ValueError("graph_tool_native_edge_occurrence_mapping_invalid")
                source = self.graph.vertex_index[edge.source()]
                target = self.graph.vertex_index[edge.target()]
                identity = (int(source), int(target))
                prior = selected.get(occurrence)
                if prior is not None:
                    prior_edge, prior_identity = prior
                    if prior_identity != identity or int(self.graph.edge_index[prior_edge]) != native_edge_id:
                        raise ValueError("graph_tool_native_edge_occurrence_duplicate")
                    continue
                selected[occurrence] = (edge, identity)

        if direction in (TraversalDirection.OUTGOING, TraversalDirection.BOTH):
            self._adjacency_metrics["outgoing_edge_iterator_lookups"] += 1
            collect(vertex.out_edges())
        if direction in (TraversalDirection.INCOMING, TraversalDirection.BOTH):
            self._adjacency_metrics["incoming_edge_iterator_lookups"] += 1
            collect(vertex.in_edges())

        vp = self.graph.vertex_properties
        ep = self.graph.edge_properties
        records = []
        for occurrence in sorted(selected):
            edge, _identity = selected[occurrence]
            observed_occurrence = ep["semantic_occurrence"][edge]
            if type(observed_occurrence) is not int or observed_occurrence != occurrence:
                raise ValueError("graph_tool_semantic_occurrence_property_mismatch")
            source = vp["semantic_id"][edge.source()]
            target = vp["semantic_id"][edge.target()]
            canonical = self._projection.edges[occurrence]
            relation = ep["relation"][edge]
            attributes = ep["attributes"][edge]
            metadata = ep["metadata"][edge]
            if (
                source != canonical["source"]
                or target != canonical["target"]
                or relation != canonical["relation"]
                or attributes != canonical["attributes"]
                or metadata != canonical["metadata"]
            ):
                raise ValueError("native_edge_projection_semantic_mismatch")
            records.append(NativeEdgeOccurrence(
                occurrence_id=occurrence,
                source_id=source,
                target_id=target,
                relation_type=relation,
                attributes=deepcopy(attributes),
                metadata=deepcopy(metadata),
                backend_edge_ref=("graph-tool", int(self.graph.edge_index[edge]), occurrence),
            ))
        self._adjacency_metrics["native_edge_occurrences_read"] += len(records)
        return tuple(records)

    def native_adjacency_report(self):
        return dict(self._adjacency_metrics)
