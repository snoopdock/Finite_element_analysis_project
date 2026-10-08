"""Immutable, content-addressed semantic graph snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph.analysis.context import SemanticContext
from audit_engine.semantic_audit.graph.analysis.identity import (
    deterministic_id,
    edge_fingerprint,
    graph_fingerprint,
)

from ._freeze import freeze, thaw


GRAPH_SNAPSHOT_SCHEMA_VERSION = 'semantic_graph_snapshot/v1'


@dataclass(frozen=True)
class NodeSnapshot:
    node_id: str
    entity_type: str
    attributes: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, 'attributes', freeze(dict(self.attributes)))
        object.__setattr__(self, 'metadata', freeze(dict(self.metadata)))

    @classmethod
    def from_node(cls, node: SemanticNode) -> 'NodeSnapshot':
        return cls(
            node_id=node.node_id,
            entity_type=node.entity_type,
            attributes=dict(node.attributes),
            metadata=dict(node.metadata),
        )

    @property
    def fingerprint(self) -> str:
        return deterministic_id('node', self.to_dict(), length=24)

    def to_dict(self) -> dict[str, Any]:
        return {
            'id': self.node_id,
            'type': self.entity_type,
            'attributes': thaw(self.attributes),
            'metadata': thaw(self.metadata),
        }


@dataclass(frozen=True)
class EdgeSnapshot:
    edge_id: str
    edge_fingerprint: str
    occurrence_index: int
    source_id: str
    target_id: str
    relation_type: str
    attributes: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, 'attributes', freeze(dict(self.attributes)))
        object.__setattr__(self, 'metadata', freeze(dict(self.metadata)))

    @classmethod
    def from_edge(cls, edge: SemanticEdge, occurrence_index: int = 0) -> 'EdgeSnapshot':
        semantic_fingerprint = edge_fingerprint(edge)
        occurrence_id = deterministic_id(
            'edge-occurrence',
            {'edge_fingerprint': semantic_fingerprint, 'occurrence_index': occurrence_index},
            length=28,
        )
        return cls(
            edge_id=occurrence_id,
            edge_fingerprint=semantic_fingerprint,
            occurrence_index=occurrence_index,
            source_id=edge.source_id,
            target_id=edge.target_id,
            relation_type=edge.relation_type,
            attributes=dict(edge.attributes),
            metadata=dict(edge.metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            'edge_id': self.edge_id,
            'edge_fingerprint': self.edge_fingerprint,
            'occurrence_index': self.occurrence_index,
            'source': self.source_id,
            'target': self.target_id,
            'relation': self.relation_type,
            'attributes': thaw(self.attributes),
            'metadata': thaw(self.metadata),
        }


@dataclass(frozen=True)
class GraphSnapshot:
    snapshot_id: str
    graph_fingerprint: str
    semantic_context: SemanticContext
    nodes: tuple[NodeSnapshot, ...]
    edges: tuple[EdgeSnapshot, ...]
    parent_snapshot_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = GRAPH_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, 'nodes', tuple(sorted(self.nodes, key=lambda value: value.node_id)))
        object.__setattr__(
            self,
            'edges',
            tuple(
                sorted(
                    self.edges,
                    key=lambda value: (
                        value.source_id,
                        value.target_id,
                        value.relation_type,
                        value.edge_id,
                    ),
                )
            ),
        )
        object.__setattr__(self, 'metadata', freeze(dict(self.metadata)))

    @classmethod
    def capture(
        cls,
        graph: SemanticGraph,
        *,
        semantic_context: SemanticContext | None = None,
        parent_snapshot_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> 'GraphSnapshot':
        context = semantic_context or SemanticContext()
        node_records = tuple(NodeSnapshot.from_node(node) for node in graph.nodes)
        edge_occurrences: dict[str, int] = {}
        edge_records_list = []
        for edge in graph.edges:
            semantic_fingerprint = edge_fingerprint(edge)
            occurrence_index = edge_occurrences.get(semantic_fingerprint, 0)
            edge_occurrences[semantic_fingerprint] = occurrence_index + 1
            edge_records_list.append(EdgeSnapshot.from_edge(edge, occurrence_index))
        edge_records = tuple(edge_records_list)
        graph_id = graph_fingerprint(graph)
        snapshot_metadata = dict(metadata or {})
        identity_payload = {
            'graph_fingerprint': graph_id,
            'semantic_context_fingerprint': context.fingerprint,
            'parent_snapshot_id': parent_snapshot_id,
            'metadata': snapshot_metadata,
        }
        return cls(
            snapshot_id=deterministic_id('graph-snapshot', identity_payload, length=28),
            graph_fingerprint=graph_id,
            semantic_context=context,
            nodes=node_records,
            edges=edge_records,
            parent_snapshot_id=parent_snapshot_id,
            metadata=snapshot_metadata,
        )

    @property
    def semantic_context_fingerprint(self) -> str:
        return self.semantic_context.fingerprint

    def node_map(self) -> dict[str, NodeSnapshot]:
        return {node.node_id: node for node in self.nodes}

    def edge_map(self) -> dict[str, EdgeSnapshot]:
        return {edge.edge_id: edge for edge in self.edges}

    def to_dict(self) -> dict[str, Any]:
        return {
            'schema_version': self.schema_version,
            'snapshot_id': self.snapshot_id,
            'graph_fingerprint': self.graph_fingerprint,
            'semantic_context': self.semantic_context.to_dict(),
            'semantic_context_fingerprint': self.semantic_context_fingerprint,
            'parent_snapshot_id': self.parent_snapshot_id,
            'nodes': [node.to_dict() for node in self.nodes],
            'edges': [edge.to_dict() for edge in self.edges],
            'metadata': thaw(self.metadata),
        }
