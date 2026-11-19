"""Hybrid SciPy CSR projection with exact canonical edge-occurrence side channels."""

from collections import defaultdict
from copy import deepcopy
from typing import Any, Dict

import numpy as np
from scipy.sparse import csr_matrix

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph
from audit_engine.semantic_audit.graph.backend.adapter_interface import SemanticGraphAdapter
from audit_engine.semantic_audit.graph.backend.optional_backend_support import make_projection


class SciPyAdapter(SemanticGraphAdapter):
    """Sparse directed adjacency backend.

    CSR stores connectivity and parallel-edge multiplicity. Exact semantic
    edge occurrences, relation labels, attributes and provenance remain in
    immutable side channels and are joined back before evidence is emitted.
    """

    def __init__(self, graph: SemanticGraph):
        self.semantic_graph = graph
        self._projection = make_projection(graph)
        self.node_to_index = dict(self._projection.node_to_index)
        self.index_to_node = {v: k for k, v in self.node_to_index.items()}
        self.relations = []
        self.metadata = {"nodes": {}, "edges": []}
        self._pair_occurrences = defaultdict(list)

        for node in self._projection.nodes:
            self.metadata["nodes"][node["id"]] = {
                "type": deepcopy(node["type"]),
                "attributes": deepcopy(node["attributes"]),
                "metadata": deepcopy(node["metadata"]),
            }

        rows, cols, values = [], [], []
        for edge in self._projection.edges:
            source_index = edge["source_index"]
            target_index = edge["target_index"]
            occurrence = edge["occurrence"]
            rows.append(source_index)
            cols.append(target_index)
            values.append(1)
            self._pair_occurrences[(source_index, target_index)].append(occurrence)
            self.relations.append({
                "source": edge["source"],
                "target": edge["target"],
                "relation": edge["relation"],
                "occurrence": occurrence,
            })
            self.metadata["edges"].append({
                "source": edge["source"],
                "target": edge["target"],
                "relation": edge["relation"],
                "attributes": deepcopy(edge["attributes"]),
                "metadata": deepcopy(edge["metadata"]),
                "occurrence": occurrence,
            })

        size = len(self._projection.nodes)
        self.matrix = csr_matrix(
            (np.asarray(values, dtype=np.int64),
             (np.asarray(rows, dtype=np.int64), np.asarray(cols, dtype=np.int64))),
            shape=(size, size),
            dtype=np.int64,
        )
        self.matrix.sum_duplicates()
        self.matrix.sort_indices()

    def _node_payload(self, node_id: str) -> dict:
        item = self.metadata["nodes"][node_id]
        return {
            "id": node_id, "type": deepcopy(item["type"]),
            "attributes": deepcopy(item["attributes"]),
            "metadata": deepcopy(item["metadata"]),
        }

    def iter_native_nodes(self):
        if self.matrix.shape != (len(self.node_to_index), len(self.node_to_index)):
            raise ValueError("scipy_projection_shape_mismatch")
        for node_id in sorted(self.node_to_index, key=self.node_to_index.get):
            yield self._node_payload(node_id)

    def iter_native_edges(self):
        if not isinstance(self.matrix, csr_matrix):
            raise ValueError("scipy_projection_not_csr")
        if self.matrix.shape != (len(self.node_to_index), len(self.node_to_index)):
            raise ValueError("scipy_projection_shape_mismatch")
        seen = set()
        for source_index in range(self.matrix.shape[0]):
            start = int(self.matrix.indptr[source_index])
            stop = int(self.matrix.indptr[source_index + 1])
            for position in range(start, stop):
                target_index = int(self.matrix.indices[position])
                stored_count = int(self.matrix.data[position])
                occurrences = self._pair_occurrences.get((source_index, target_index), ())
                if stored_count != len(occurrences) or not occurrences:
                    raise ValueError("scipy_projection_multiplicity_mismatch")
                for occurrence in occurrences:
                    if occurrence in seen:
                        raise ValueError("scipy_projection_duplicate_edge_occurrence")
                    seen.add(occurrence)
                    relation_sidecar = self.relations[occurrence]
                    edge_sidecar = self.metadata["edges"][occurrence]
                    if (
                        relation_sidecar.get("source") != self.index_to_node[source_index]
                        or relation_sidecar.get("target") != self.index_to_node[target_index]
                        or edge_sidecar.get("source") != relation_sidecar.get("source")
                        or edge_sidecar.get("target") != relation_sidecar.get("target")
                        or edge_sidecar.get("relation") != relation_sidecar.get("relation")
                        or edge_sidecar.get("occurrence") != occurrence
                    ):
                        raise ValueError("scipy_projection_side_channel_identity_mismatch")
                    yield {
                        "occurrence": occurrence,
                        "source": relation_sidecar["source"],
                        "target": relation_sidecar["target"],
                        "relation": relation_sidecar["relation"],
                        "attributes": deepcopy(edge_sidecar["attributes"]),
                        "metadata": deepcopy(edge_sidecar["metadata"]),
                    }
        if len(seen) != len(self._projection.edges):
            raise ValueError("scipy_projection_edge_count_mismatch")

    def export(self):
        return self.matrix

    def backend_graph(self):
        return self.matrix

    def nodes(self):
        return list(self.node_to_index)

    def edges(self):
        return [
            {"relation": item["relation"], "attributes": deepcopy(item["attributes"]),
             "metadata": deepcopy(item["metadata"])}
            for item in self._projection.edges
        ]

    def neighbors(self, node_id):
        if node_id not in self.node_to_index:
            raise KeyError(node_id)
        index = self.node_to_index[node_id]
        start, stop = int(self.matrix.indptr[index]), int(self.matrix.indptr[index + 1])
        return [self.index_to_node[int(i)] for i in self.matrix.indices[start:stop]]

    def capabilities(self) -> Dict[str, Any]:
        return {
            "backend": "scipy",
            "sparse_matrix": True,
            "directed_graph": True,
            "multiedges": True,
            "matrix_native_multiedges": False,
            "semantic_edge_occurrences": True,
            "metadata": True,
            "relation_labels": True,
            "side_channel_preservation": True,
            "lossless": False,
        }

    def identity_mapping(self):
        return {
            "semantic_to_index": dict(self.node_to_index),
            "index_to_semantic": dict(self.index_to_node),
            "semantic_edge_occurrence_to_backend": {
                i: i for i in range(len(self._projection.edges))
            },
            "backend_to_semantic_edge_occurrence": {
                i: i for i in range(len(self._projection.edges))
            },
        }

    def loss_report(self):
        return {
            "lossless": False,
            "preserved": [
                "directed_connectivity",
                "parallel_edge_multiplicity",
                "semantic_node_identity_mapping",
                "exact_edge_occurrences_in_side_channel",
                "relation_labels_in_side_channel",
                "node_and_edge_attributes_in_side_channel",
                "node_and_edge_metadata_in_side_channel",
            ],
            "transformed": [
                "parallel_edges_collapsed_to_csr_multiplicity",
                "semantic_edge_payloads_joined_from_side_channel",
            ],
            "lost": [
                "native_per_edge_relation_and_metadata_columns_inside_csr_matrix",
            ],
            "scope": "hybrid_csr_plus_exact_semantic_side_channels",
        }
