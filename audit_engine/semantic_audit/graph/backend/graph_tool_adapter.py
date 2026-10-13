"""Native graph-tool projection using vertex and edge property maps.

Object-valued property maps are intended for in-process computation; they are
not claimed to survive graph-tool's binary/XML serialization.
"""

from audit_engine.semantic_audit.graph.backend.adapter_interface import SemanticGraphAdapter
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
                node_props[prop_name][vertex] = node[field]
        for edge in data.edges:
            e = native.add_edge(native.vertex(edge["source_index"]),
                                native.vertex(edge["target_index"]))
            for prop_name, field in (
                ("relation", "relation"), ("attributes", "attributes"),
                ("metadata", "metadata"), ("semantic_occurrence", "occurrence"),
            ):
                edge_props[prop_name][e] = edge[field]
        self.semantic_graph = graph
        self._projection = data
        self._index = dict(data.node_to_index)
        self._edge_ids = {e["occurrence"]: e["occurrence"] for e in data.edges}
        self.graph = native

    def loss_report(self):
        report = super().loss_report()
        report["scope"] = "in_memory_only; Python-object property maps are not portable graph-tool files"
        return report
