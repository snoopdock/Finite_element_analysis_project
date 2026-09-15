from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class SemanticNode:
    """
    Represents an identifiable semantic entity.

    The core intentionally does not impose a closed domain vocabulary.
    Examples include software modules, functions, scientific claims,
    documents, concepts, equations, evidence items, and source records.

    RDF compatibility:
    node_id may later map to an RDF resource identifier.
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
    Represents a directed typed semantic relationship.

    The core intentionally does not impose a closed relation vocabulary.
    Examples include IMPORTS, CALLS, SUPPORTED_BY, DERIVED_FROM,
    REFERENCES, DEFINES, and other domain-specific relations.

    RDF compatibility:
    relation_type may later map to an RDF predicate.
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

    The graph is designed as a directed attributed multigraph.

    Core integrity invariants:
    - node_id is unique within one graph snapshot
    - an edge may only reference nodes already present in the graph
    - parallel edges are allowed
    - self-loops are allowed

    Backend libraries must adapt to this model rather than defining it.

    Candidate computational or export backends include:
    - NetworkX
    - igraph
    - graph-tool
    - SNAP
    - SciPy sparse graph operations
    - RDF/Turtle
    - OWL-compatible representations
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

        node_id is the identity key within this graph snapshot.

        Silent overwrite, merge, or duplicate insertion is prohibited.
        Identity resolution and entity merging belong to explicit
        domain-level processes rather than this core method.
        """

        if not isinstance(node.node_id, str) or not node.node_id.strip():
            raise ValueError(
                "SemanticNode.node_id must be a non-empty string."
            )

        if not isinstance(node.entity_type, str) or not node.entity_type.strip():
            raise ValueError(
                "SemanticNode.entity_type must be a non-empty string."
            )

        if self.has_node(node.node_id):
            raise ValueError(
                f"Duplicate semantic node_id: {node.node_id!r}"
            )

        self.nodes.append(
            node
        )


    def add_edge(
        self,
        edge: SemanticEdge
    ) -> None:
        """
        Add a semantic relationship.

        Canonical SemanticGraph instances do not permit dangling edges.
        Both endpoint nodes must already exist.

        Parallel relationships and self-loops remain valid because they
        can represent distinct semantic observations or relation types.
        """

        if (
            not isinstance(edge.source_id, str)
            or not edge.source_id.strip()
        ):
            raise ValueError(
                "SemanticEdge.source_id must be a non-empty string."
            )

        if (
            not isinstance(edge.target_id, str)
            or not edge.target_id.strip()
        ):
            raise ValueError(
                "SemanticEdge.target_id must be a non-empty string."
            )

        if (
            not isinstance(edge.relation_type, str)
            or not edge.relation_type.strip()
        ):
            raise ValueError(
                "SemanticEdge.relation_type must be a non-empty string."
            )

        missing_nodes = []

        if not self.has_node(edge.source_id):
            missing_nodes.append(
                edge.source_id
            )

        if not self.has_node(edge.target_id):
            missing_nodes.append(
                edge.target_id
            )

        if missing_nodes:
            missing_display = ", ".join(
                repr(node_id)
                for node_id in missing_nodes
            )

            raise ValueError(
                "SemanticEdge references node(s) not present "
                f"in the graph: {missing_display}"
            )

        self.edges.append(
            edge
        )


    def get_node(
        self,
        node_id: str
    ) -> SemanticNode | None:
        """
        Retrieve a node by semantic identifier.
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
        Check whether a semantic node identifier exists.
        """

        return self.get_node(
            node_id
        ) is not None


    def to_dict(self) -> dict:
        """
        Convert the graph into the current portable JSON-compatible form.

        The serialized field names intentionally differ from some
        in-memory names:

        node_id       -> id
        entity_type   -> type
        source_id     -> source
        target_id     -> target
        relation_type -> relation

        The payload shape remains unchanged from the G2/G2.5 contract.
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
