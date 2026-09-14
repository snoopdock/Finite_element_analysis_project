"""
NetworkX backend adapter for SemanticGraph.

This module provides computational capabilities
without changing the semantic graph model.

NetworkX is treated only as a backend.
"""


from typing import List, Dict, Any

import networkx as nx

from ...core.semantic_graph import (
    SemanticGraph,
    SemanticNode,
    SemanticEdge,
)


class NetworkXAdapter:
    """
    Adapter between SemanticGraph and NetworkX MultiDiGraph.

    The SemanticGraph remains the authoritative model.

    NetworkX is only used for:
        - traversal
        - analysis
        - visualization
    """

    def __init__(self, graph: SemanticGraph):

        self.semantic_graph = graph

        self._graph = nx.MultiDiGraph()

        self._load_graph()


    def _load_graph(self) -> None:
        """
        Convert universal SemanticGraph into NetworkX representation.

        NetworkX is only a computational backend.
        The semantic graph remains authoritative.
        """

        for node in self.semantic_graph.nodes:

            self._graph.add_node(

                node.node_id,

                entity_type=node.entity_type,

                metadata=node.metadata,

                **node.attributes

            )


        for edge in self.semantic_graph.edges:

            self._graph.add_edge(

                edge.source_id,

                edge.target_id,

                relation=edge.relation_type,

                metadata=edge.metadata,

                **edge.attributes

            )


    def nodes(self) -> List[str]:
        """
        Return node identifiers.
        """

        return list(self._graph.nodes)



    def edges(self) -> List[Dict[str, Any]]:
        """
        Return graph relationships.
        """

        result = []

        for source, target, data in self._graph.edges(
            data=True
        ):

            result.append(
                {
                    "source": source,
                    "target": target,
                    **data
                }
            )

        return result



    def neighbors(
        self,
        node_id: str
    ) -> List[str]:

        """
        Return outgoing relationships.
        """

        return list(
            self._graph.successors(node_id)
        )



    def predecessors(
        self,
        node_id: str
    ) -> List[str]:

        """
        Return incoming relationships.
        """

        return list(
            self._graph.predecessors(node_id)
        )



    def find_paths(
        self,
        source: str,
        target: str
    ):

        """
        Find directed paths between nodes.
        """

        return list(
            nx.all_simple_paths(
                self._graph,
                source,
                target
            )
        )



    def degree(
        self,
        node_id: str
    ) -> int:

        """
        Return total graph degree.
        """

        return self._graph.degree(node_id)



    def backend_graph(self):
        """
        Expose NetworkX graph for advanced operations.

        Use carefully.

        The semantic graph should still be modified
        through SemanticGraph APIs.
        """

        return self._graph
