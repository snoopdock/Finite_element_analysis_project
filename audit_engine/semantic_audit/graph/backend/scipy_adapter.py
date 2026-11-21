"""Hybrid SciPy CSR projection with exact canonical edge-occurrence side channels."""

from collections import defaultdict
from copy import deepcopy
from typing import Any, Dict

import numpy as np
from scipy.sparse import csc_matrix, csr_matrix

from audit_engine.semantic_audit.graph.analysis.models import TraversalDirection
from audit_engine.semantic_audit.graph.backend.adapter_interface import NativeEdgeOccurrence

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
        # CSR is the authoritative outgoing index. CSC is a one-time native
        # transpose index for incoming queries; neither query path scans edges.
        self.matrix_csc = self.matrix.tocsc(copy=True)
        self.matrix_csc.sort_indices()
        self._adjacency_metrics = {
            "native_adjacency_lookups": 0,
            "csr_row_lookups": 0,
            "csc_column_lookups": 0,
            "native_pair_entries_read": 0,
            "native_edge_occurrences_read": 0,
        }

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
        if not isinstance(self.matrix_csc, csc_matrix):
            raise ValueError("scipy_projection_not_csc")
        expected_shape = (len(self.node_to_index), len(self.node_to_index))
        if self.matrix.shape != expected_shape or self.matrix_csc.shape != expected_shape:
            raise ValueError("scipy_projection_shape_mismatch")
        if (self.matrix.tocsc() != self.matrix_csc).nnz:
            raise ValueError("scipy_csr_csc_index_mismatch")
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


    def _occurrences_for_pair(self, source_index: int, target_index: int, stored_count: int):
        """Resolve one native sparse coordinate to its exact edge occurrences."""
        if isinstance(stored_count, bool) or stored_count < 1:
            raise ValueError("scipy_projection_multiplicity_invalid")
        occurrences = self._pair_occurrences.get((source_index, target_index), ())
        if len(occurrences) != stored_count:
            raise ValueError("scipy_projection_multiplicity_mismatch")
        source_id = self.index_to_node[source_index]
        target_id = self.index_to_node[target_index]
        records = []
        for occurrence in occurrences:
            if type(occurrence) is not int or not 0 <= occurrence < len(self.metadata["edges"]):
                raise ValueError("scipy_projection_occurrence_invalid")
            relation = self.relations[occurrence]
            payload = self.metadata["edges"][occurrence]
            if (
                relation.get("occurrence") != occurrence
                or relation.get("source") != source_id
                or relation.get("target") != target_id
                or payload.get("occurrence") != occurrence
                or payload.get("source") != source_id
                or payload.get("target") != target_id
                or payload.get("relation") != relation.get("relation")
            ):
                raise ValueError("scipy_projection_side_channel_identity_mismatch")
            records.append(NativeEdgeOccurrence(
                occurrence_id=occurrence,
                source_id=source_id,
                target_id=target_id,
                relation_type=relation["relation"],
                attributes=deepcopy(payload["attributes"]),
                metadata=deepcopy(payload["metadata"]),
                backend_edge_ref=("scipy", source_index, target_index, occurrence),
            ))
        return records

    def iter_adjacent_edge_occurrences(self, node_id: str, direction: TraversalDirection):
        """Read only the requested CSR row and/or CSC column.

        Parallel edges are expanded through the occurrence side channel. BOTH
        is a set union by occurrence ID, so a self-loop is returned once.
        """
        if node_id not in self.node_to_index:
            raise KeyError(node_id)
        if isinstance(direction, str):
            direction = TraversalDirection(direction)
        if not isinstance(direction, TraversalDirection):
            raise ValueError("scipy_adjacency_direction_invalid")

        self._adjacency_metrics["native_adjacency_lookups"] += 1
        index = self.node_to_index[node_id]
        records_by_occurrence = {}

        if direction in (TraversalDirection.OUTGOING, TraversalDirection.BOTH):
            self._adjacency_metrics["csr_row_lookups"] += 1
            start = int(self.matrix.indptr[index])
            stop = int(self.matrix.indptr[index + 1])
            for position in range(start, stop):
                target_index = int(self.matrix.indices[position])
                count = int(self.matrix.data[position])
                self._adjacency_metrics["native_pair_entries_read"] += 1
                for record in self._occurrences_for_pair(index, target_index, count):
                    records_by_occurrence[record.occurrence_id] = record

        if direction in (TraversalDirection.INCOMING, TraversalDirection.BOTH):
            self._adjacency_metrics["csc_column_lookups"] += 1
            start = int(self.matrix_csc.indptr[index])
            stop = int(self.matrix_csc.indptr[index + 1])
            for position in range(start, stop):
                source_index = int(self.matrix_csc.indices[position])
                count = int(self.matrix_csc.data[position])
                self._adjacency_metrics["native_pair_entries_read"] += 1
                for record in self._occurrences_for_pair(source_index, index, count):
                    records_by_occurrence[record.occurrence_id] = record

        records = [records_by_occurrence[key] for key in sorted(records_by_occurrence)]
        self._adjacency_metrics["native_edge_occurrences_read"] += len(records)
        return tuple(records)

    def native_adjacency_report(self) -> dict:
        """Return counters only; reporting never enumerates the sparse graph."""
        return dict(self._adjacency_metrics)

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
