"""Native python-igraph projection of the canonical directed semantic multigraph."""

from audit_engine.semantic_audit.graph.backend.adapter_interface import SemanticGraphAdapter
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
