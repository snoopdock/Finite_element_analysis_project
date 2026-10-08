"""Semantic graph snapshot differencing without backend-specific graph types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from audit_engine.semantic_audit.graph.analysis.identity import deterministic_id

from .snapshots import EdgeSnapshot, GraphSnapshot, NodeSnapshot


GRAPH_DELTA_SCHEMA_VERSION = 'semantic_graph_delta/v1'


@dataclass(frozen=True)
class SemanticContextDelta:
    changed_fields: tuple[tuple[str, Any, Any], ...] = field(default_factory=tuple)

    @property
    def changed(self) -> bool:
        return bool(self.changed_fields)

    @classmethod
    def compare(cls, before: GraphSnapshot, after: GraphSnapshot) -> 'SemanticContextDelta':
        left = before.semantic_context.to_dict()
        right = after.semantic_context.to_dict()
        keys = sorted(set(left) | set(right))
        changes = tuple((key, left.get(key), right.get(key)) for key in keys if left.get(key) != right.get(key))
        return cls(changed_fields=changes)

    def to_dict(self) -> dict[str, Any]:
        return {
            'changed': self.changed,
            'changed_fields': [
                {'field': field_name, 'before': before, 'after': after}
                for field_name, before, after in self.changed_fields
            ],
        }


@dataclass(frozen=True)
class NodeMutation:
    node_id: str
    before: NodeSnapshot
    after: NodeSnapshot

    def to_dict(self) -> dict[str, Any]:
        return {
            'node_id': self.node_id,
            'before_fingerprint': self.before.fingerprint,
            'after_fingerprint': self.after.fingerprint,
            'before': self.before.to_dict(),
            'after': self.after.to_dict(),
        }


@dataclass(frozen=True)
class GraphDelta:
    delta_id: str
    before_snapshot_id: str
    after_snapshot_id: str
    added_nodes: tuple[NodeSnapshot, ...] = field(default_factory=tuple)
    removed_nodes: tuple[NodeSnapshot, ...] = field(default_factory=tuple)
    modified_nodes: tuple[NodeMutation, ...] = field(default_factory=tuple)
    added_edges: tuple[EdgeSnapshot, ...] = field(default_factory=tuple)
    removed_edges: tuple[EdgeSnapshot, ...] = field(default_factory=tuple)
    fully_removed_edge_fingerprints: tuple[str, ...] = field(default_factory=tuple)
    semantic_context_delta: SemanticContextDelta = field(default_factory=SemanticContextDelta)
    schema_version: str = GRAPH_DELTA_SCHEMA_VERSION

    @property
    def is_noop(self) -> bool:
        return not any(
            (
                self.added_nodes,
                self.removed_nodes,
                self.modified_nodes,
                self.added_edges,
                self.removed_edges,
                self.semantic_context_delta.changed,
            )
        )

    @property
    def removed_evidence_ids(self) -> tuple[str, ...]:
        return self.fully_removed_edge_fingerprints

    def to_dict(self) -> dict[str, Any]:
        return {
            'schema_version': self.schema_version,
            'delta_id': self.delta_id,
            'before_snapshot_id': self.before_snapshot_id,
            'after_snapshot_id': self.after_snapshot_id,
            'is_noop': self.is_noop,
            'added_nodes': [value.to_dict() for value in self.added_nodes],
            'removed_nodes': [value.to_dict() for value in self.removed_nodes],
            'modified_nodes': [value.to_dict() for value in self.modified_nodes],
            'added_edges': [value.to_dict() for value in self.added_edges],
            'removed_edges': [value.to_dict() for value in self.removed_edges],
            'fully_removed_edge_fingerprints': list(self.fully_removed_edge_fingerprints),
            'semantic_context_delta': self.semantic_context_delta.to_dict(),
        }


def compare_snapshots(before: GraphSnapshot, after: GraphSnapshot) -> GraphDelta:
    before_nodes = before.node_map()
    after_nodes = after.node_map()
    before_edges = before.edge_map()
    after_edges = after.edge_map()

    added_nodes = tuple(after_nodes[node_id] for node_id in sorted(set(after_nodes) - set(before_nodes)))
    removed_nodes = tuple(before_nodes[node_id] for node_id in sorted(set(before_nodes) - set(after_nodes)))
    modified_nodes = tuple(
        NodeMutation(node_id=node_id, before=before_nodes[node_id], after=after_nodes[node_id])
        for node_id in sorted(set(before_nodes) & set(after_nodes))
        if before_nodes[node_id].fingerprint != after_nodes[node_id].fingerprint
    )
    added_edges = tuple(after_edges[edge_id] for edge_id in sorted(set(after_edges) - set(before_edges)))
    removed_edges = tuple(before_edges[edge_id] for edge_id in sorted(set(before_edges) - set(after_edges)))
    before_semantic_edge_fingerprints = {edge.edge_fingerprint for edge in before.edges}
    after_semantic_edge_fingerprints = {edge.edge_fingerprint for edge in after.edges}
    fully_removed_edge_fingerprints = tuple(sorted(before_semantic_edge_fingerprints - after_semantic_edge_fingerprints))
    context_delta = SemanticContextDelta.compare(before, after)

    payload = {
        'before_snapshot_id': before.snapshot_id,
        'after_snapshot_id': after.snapshot_id,
        'added_node_ids': [value.node_id for value in added_nodes],
        'removed_node_ids': [value.node_id for value in removed_nodes],
        'modified_nodes': [
            [value.node_id, value.before.fingerprint, value.after.fingerprint]
            for value in modified_nodes
        ],
        'added_edge_ids': [value.edge_id for value in added_edges],
        'removed_edge_ids': [value.edge_id for value in removed_edges],
        'fully_removed_edge_fingerprints': list(fully_removed_edge_fingerprints),
        'semantic_context_delta': context_delta.to_dict(),
    }
    return GraphDelta(
        delta_id=deterministic_id('graph-delta', payload, length=28),
        before_snapshot_id=before.snapshot_id,
        after_snapshot_id=after.snapshot_id,
        added_nodes=added_nodes,
        removed_nodes=removed_nodes,
        modified_nodes=modified_nodes,
        added_edges=added_edges,
        removed_edges=removed_edges,
        fully_removed_edge_fingerprints=fully_removed_edge_fingerprints,
        semantic_context_delta=context_delta,
    )
