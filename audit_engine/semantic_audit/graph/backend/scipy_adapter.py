from typing import Any, Dict

import numpy as np
from scipy.sparse import csr_matrix

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph
from audit_engine.semantic_audit.graph.backend.adapter_interface import (
    SemanticGraphAdapter,
)


class SciPyAdapter(SemanticGraphAdapter):
    """
    Hybrid SciPy projection adapter.

    SemanticGraph remains the source of truth.

    Projection artifacts:

    - sparse adjacency matrix
    - semantic/index mappings
    - relation side-channel
    - metadata side-channel
    """

    def __init__(self, graph: SemanticGraph):
        self.semantic_graph = graph

        self.node_to_index = {}
        self.index_to_node = {}

        self.relations = []
        self.metadata = {
            "nodes": {},
            "edges": [],
        }

        self.matrix = self._build_matrix()


    def _build_matrix(self):
        rows = []
        cols = []
        data = []

        for index, node in enumerate(self.semantic_graph.nodes):
            self.node_to_index[node.node_id] = index
            self.index_to_node[index] = node.node_id

            self.metadata["nodes"][node.node_id] = {
                "type": node.entity_type,
                "attributes": node.attributes,
                "metadata": node.metadata,
            }

        for edge in self.semantic_graph.edges:

            source = self.node_to_index[edge.source_id]
            target = self.node_to_index[edge.target_id]

            rows.append(source)
            cols.append(target)
            data.append(1)

            self.relations.append({
                "source": edge.source_id,
                "target": edge.target_id,
                "relation": edge.relation_type,
            })

            self.metadata["edges"].append({
                "source": edge.source_id,
                "target": edge.target_id,
                "attributes": edge.attributes,
                "metadata": edge.metadata,
            })

        size = len(self.semantic_graph.nodes)

        return csr_matrix(
            (
                data,
                (rows, cols)
            ),
            shape=(size, size),
        )


    def export(self):
        return self.matrix


    def capabilities(self) -> Dict[str, Any]:

        return {
            "backend": "scipy",
            "sparse_matrix": True,
            "directed_graph": True,
            "multiedges": False,
            "metadata": False,
            "relation_labels": False,
            "lossless": False,
        }


    def identity_mapping(self):

        return {
            "semantic_to_index": dict(self.node_to_index),
            "index_to_semantic": dict(self.index_to_node),
        }


    def loss_report(self):

        return {
            "preserved": [
                "connectivity",
                "direction",
                "node_index_mapping",
            ],
            "transformed": [
                "semantic_edges_to_numeric_entries",
            ],
            "lost": [
                "direct_relation_representation_inside_matrix",
                "metadata_inside_matrix",
            ],
        }
