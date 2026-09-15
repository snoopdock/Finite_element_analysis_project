from typing import Any, Dict

import networkx as nx

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph
from audit_engine.semantic_audit.graph.backend.adapter_interface import (
    SemanticGraphAdapter,
)


class NetworkXAdapter(SemanticGraphAdapter):
    """
    Official NetworkX projection adapter.

    SemanticGraph remains the source of truth.

    This class converts the universal semantic representation into a
    NetworkX MultiDiGraph while preserving:

    - semantic node identifiers
    - node entity types
    - node attributes
    - node metadata
    - edge relation types
    - edge attributes
    - edge metadata

    NetworkX is used only as a computational backend.
    """

    def __init__(
        self,
        graph: SemanticGraph,
    ):
        self.semantic_graph = graph

        self.graph = nx.MultiDiGraph()

        self._semantic_to_backend: Dict[str, Any] = {}

        self._backend_to_semantic: Dict[Any, str] = {}

        self._build()


    def _build(self) -> None:
        """
        Project SemanticGraph into NetworkX.
        """

        for node in self.semantic_graph.nodes:

            backend_id = node.node_id

            self._semantic_to_backend[node.node_id] = backend_id

            self._backend_to_semantic[backend_id] = node.node_id

            self.graph.add_node(
                backend_id,
                entity_type=node.entity_type,
                attributes=node.attributes,
                metadata=node.metadata,
            )


        for edge in self.semantic_graph.edges:

            source = self._semantic_to_backend[
                edge.source_id
            ]

            target = self._semantic_to_backend[
                edge.target_id
            ]

            self.graph.add_edge(
                source,
                target,
                relation=edge.relation_type,
                attributes=edge.attributes,
                metadata=edge.metadata,
            )


    def export(self) -> nx.MultiDiGraph:
        """
        Return NetworkX representation.
        """

        return self.graph


    def backend_graph(self) -> nx.MultiDiGraph:
        """
        Backward-compatible alias.
        """

        return self.graph


    def nodes(self):
        """
        Return backend node identifiers.
        """

        return list(
            self.graph.nodes
        )


    def edges(self):
        """
        Return semantic edge information from NetworkX.
        """

        result = []

        for _, _, data in self.graph.edges(
            data=True
        ):

            result.append(
                data
            )

        return result


    def neighbors(
        self,
        node_id: str,
    ):
        """
        Return outgoing semantic neighbors.
        """

        return list(
            self.graph.neighbors(
                node_id
            )
        )


    def capabilities(self) -> Dict[str, Any]:
        """
        Describe NetworkX preservation capabilities.
        """

        return {

            "backend": "networkx",

            "directed_graph": True,

            "multiedges": True,

            "self_loops": True,

            "node_attributes": True,

            "edge_attributes": True,

            "metadata": True,

            "lossless": True,

        }


    def identity_mapping(self) -> Dict[str, Dict[Any, str]]:
        """
        Return reversible semantic/backend identity mapping.
        """

        return {

            "semantic_to_backend":
                dict(
                    self._semantic_to_backend
                ),

            "backend_to_semantic":
                dict(
                    self._backend_to_semantic
                ),

        }


    def loss_report(self) -> Dict[str, Any]:
        """
        Report projection information loss.

        NetworkX MultiDiGraph can preserve all current SemanticGraph
        information used by the repository.
        """

        return {

            "lossless": True,

            "lost": [],

            "transformed": [],

        }
