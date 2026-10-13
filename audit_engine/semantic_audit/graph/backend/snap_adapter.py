"""Stanford Snap.py TNEANet projection with JSON-encoded semantic attributes.

SNAP only provides native scalar typed attribute columns. We store canonical
JSON objects in string columns and reject non-JSON Python values explicitly.
"""

import json

from audit_engine.semantic_audit.graph.backend.adapter_interface import SemanticGraphAdapter
from audit_engine.semantic_audit.graph.backend.optional_backend_support import (
    NativeAdapterMixin, make_projection, require_backend,
)


def _as_json(value, label):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"SNAP {label} cannot be encoded as canonical JSON: {exc}") from exc


class SNAPAdapter(NativeAdapterMixin, SemanticGraphAdapter):
    backend_name = "snap"

    def __init__(self, graph):
        snap = require_backend("snap")
        data = make_projection(graph)
        # Prevalidate the ENTIRE snapshot before constructing native state.
        n_attrs = [(_as_json(n["attributes"], "node attributes"),
                    _as_json(n["metadata"], "node metadata")) for n in data.nodes]
        e_attrs = [(_as_json(e["attributes"], "edge attributes"),
                    _as_json(e["metadata"], "edge metadata")) for e in data.edges]
        native = snap.TNEANet.New()
        for name in ("semantic_id", "entity_type", "attributes_json", "metadata_json"):
            native.AddStrAttrN(name)
        for name in ("relation", "attributes_json", "metadata_json"):
            native.AddStrAttrE(name)
        native.AddIntAttrE("semantic_occurrence")
        for i, node in enumerate(data.nodes):
            native.AddNode(i)
            for key, value in (
                ("semantic_id", node["id"]), ("entity_type", node["type"]),
                ("attributes_json", n_attrs[i][0]), ("metadata_json", n_attrs[i][1]),
            ):
                native.AddStrAttrDatN(i, value, key)
        edge_ids = {}
        for i, edge in enumerate(data.edges):
            native_id = native.AddEdge(edge["source_index"], edge["target_index"])
            edge_ids[edge["occurrence"]] = native_id
            for key, value in (
                ("relation", edge["relation"]), ("attributes_json", e_attrs[i][0]),
                ("metadata_json", e_attrs[i][1]),
            ):
                native.AddStrAttrDatE(native_id, value, key)
            native.AddIntAttrDatE(native_id, edge["occurrence"], "semantic_occurrence")
        self.semantic_graph = graph
        self._projection = data
        self._index = dict(data.node_to_index)
        self._edge_ids = edge_ids
        self.graph = native

    def capabilities(self):
        result = super().capabilities()
        result["json_attributes_only"] = True
        result["attributes_stored_as_json_strings"] = True
        return result

    def loss_report(self):
        result = super().loss_report()
        result["transformed"].append("attributes_encoded_as_canonical_json")
        result["scope"] = "JSON-compatible attribute dictionaries only"
        return result
