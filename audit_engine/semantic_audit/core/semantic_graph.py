from dataclasses import dataclass, field
from typing import Dict, List, Any


@dataclass
class SemanticNode:
    """
    Represents an entity inside the semantic graph.

    Examples:
    - Python module
    - Function
    - Class
    - Contract
    - Scientific article
    - Claim

    RDF compatibility:
    Node identity maps to an RDF resource.
    """

    node_id: str

    entity_type: str

    attributes: Dict[str, Any] = field(
        default_factory=dict
    )

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )


@dataclass
class SemanticEdge:
    """
    Represents a typed relationship between two semantic entities.

    Examples:
    - IMPORTS
    - CALLS
    - READS
    - WRITES
    - MUTATES
    - SUPPORTS
    - DERIVED_FROM

    RDF compatibility:
    relation_type maps to an RDF predicate.
    """

    source_id: str

    target_id: str

    relation_type: str

    attributes: Dict[str, Any] = field(
        default_factory=dict
    )

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )


@dataclass
class SemanticGraph:
    """
    Library-independent semantic graph representation.

    Designed as a directed attributed multigraph.

    Future backends:
    - NetworkX
    - igraph
    - graph-tool
    - SNAP
    - SciPy sparse graphs

    Future exports:
    - RDF/Turtle
    - OWL-compatible structures
    - Formal verification models
    """

    nodes: List[SemanticNode] = field(
        default_factory=list
    )

    edges: List[SemanticEdge] = field(
        default_factory=list
    )


    def add_node(
        self,
        node: SemanticNode
    ) -> None:
        """
        Add a semantic entity.
        """

        self.nodes.append(
            node
        )


    def add_edge(
        self,
        edge: SemanticEdge
    ) -> None:
        """
        Add a semantic relationship.
        """

        self.edges.append(
            edge
        )


    def get_node(
        self,
        node_id: str
    ) -> SemanticNode | None:
        """
        Retrieve a node by identifier.
        """

        for node in self.nodes:

            if node.node_id == node_id:
                return node

        return None


    def has_node(
        self,
        node_id: str
    ) -> bool:
        """
        Check whether a node exists.
        """

        return self.get_node(
            node_id
        ) is not None


    def to_dict(self) -> dict:
        """
        Convert graph into a JSON-compatible structure.

        This structure is intentionally RDF-friendly.
        """

        return {

            "nodes": [

                {

                    "id": node.node_id,

                    "type": node.entity_type,

                    "attributes": node.attributes,

                    "metadata": node.metadata

                }

                for node in self.nodes

            ],


            "edges": [

                {

                    "source": edge.source_id,

                    "target": edge.target_id,

                    "relation": edge.relation_type,

                    "attributes": edge.attributes,

                    "metadata": edge.metadata

                }

                for edge in self.edges

            ]

        }
