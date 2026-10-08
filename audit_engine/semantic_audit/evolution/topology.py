"""Backend-independent descriptive topology summaries for graph evolution.

These metrics are structural observations only. They must not be interpreted as
scientific importance, correctness, severity, or policy violations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from audit_engine.semantic_audit.graph.analysis.identity import deterministic_id

from .snapshots import GraphSnapshot


TOPOLOGY_SUMMARY_SCHEMA_VERSION = 'semantic_topology_summary/v1'
TOPOLOGY_DELTA_SCHEMA_VERSION = 'semantic_topology_delta/v1'


@dataclass(frozen=True)
class DegreeRecord:
    node_id: str
    in_degree: int
    out_degree: int

    @property
    def total_degree(self) -> int:
        return self.in_degree + self.out_degree

    def to_dict(self) -> dict[str, Any]:
        return {
            'node_id': self.node_id,
            'in_degree': self.in_degree,
            'out_degree': self.out_degree,
            'total_degree': self.total_degree,
        }


@dataclass(frozen=True)
class TopologySummary:
    summary_id: str
    snapshot_id: str
    node_count: int
    edge_count: int
    self_loop_count: int
    weak_component_count: int
    isolated_node_ids: tuple[str, ...]
    degrees: tuple[DegreeRecord, ...]
    relation_counts: tuple[tuple[str, int], ...]
    schema_version: str = TOPOLOGY_SUMMARY_SCHEMA_VERSION

    def degree_map(self) -> dict[str, DegreeRecord]:
        return {value.node_id: value for value in self.degrees}

    def relation_count_map(self) -> dict[str, int]:
        return dict(self.relation_counts)

    def to_dict(self) -> dict[str, Any]:
        return {
            'schema_version': self.schema_version,
            'summary_id': self.summary_id,
            'snapshot_id': self.snapshot_id,
            'node_count': self.node_count,
            'edge_count': self.edge_count,
            'self_loop_count': self.self_loop_count,
            'weak_component_count': self.weak_component_count,
            'isolated_node_ids': list(self.isolated_node_ids),
            'degrees': [value.to_dict() for value in self.degrees],
            'relation_counts': [
                {'relation_type': relation_type, 'count': count}
                for relation_type, count in self.relation_counts
            ],
            'interpretation_boundary': 'descriptive_topology_only',
        }


@dataclass(frozen=True)
class DegreeChange:
    node_id: str
    before: DegreeRecord | None
    after: DegreeRecord | None

    def to_dict(self) -> dict[str, Any]:
        return {
            'node_id': self.node_id,
            'before': None if self.before is None else self.before.to_dict(),
            'after': None if self.after is None else self.after.to_dict(),
        }


@dataclass(frozen=True)
class RelationCountChange:
    relation_type: str
    before_count: int
    after_count: int

    @property
    def delta(self) -> int:
        return self.after_count - self.before_count

    def to_dict(self) -> dict[str, Any]:
        return {
            'relation_type': self.relation_type,
            'before_count': self.before_count,
            'after_count': self.after_count,
            'delta': self.delta,
        }


@dataclass(frozen=True)
class TopologyDelta:
    topology_delta_id: str
    before_snapshot_id: str
    after_snapshot_id: str
    node_count_delta: int
    edge_count_delta: int
    self_loop_count_delta: int
    weak_component_count_delta: int
    degree_changes: tuple[DegreeChange, ...] = field(default_factory=tuple)
    relation_count_changes: tuple[RelationCountChange, ...] = field(default_factory=tuple)
    became_isolated: tuple[str, ...] = field(default_factory=tuple)
    no_longer_isolated: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = TOPOLOGY_DELTA_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            'schema_version': self.schema_version,
            'topology_delta_id': self.topology_delta_id,
            'before_snapshot_id': self.before_snapshot_id,
            'after_snapshot_id': self.after_snapshot_id,
            'node_count_delta': self.node_count_delta,
            'edge_count_delta': self.edge_count_delta,
            'self_loop_count_delta': self.self_loop_count_delta,
            'weak_component_count_delta': self.weak_component_count_delta,
            'degree_changes': [value.to_dict() for value in self.degree_changes],
            'relation_count_changes': [value.to_dict() for value in self.relation_count_changes],
            'became_isolated': list(self.became_isolated),
            'no_longer_isolated': list(self.no_longer_isolated),
            'interpretation_boundary': 'descriptive_topology_only',
        }


def _weak_component_count(snapshot: GraphSnapshot) -> int:
    adjacency: dict[str, set[str]] = {node.node_id: set() for node in snapshot.nodes}
    for edge in snapshot.edges:
        adjacency[edge.source_id].add(edge.target_id)
        adjacency[edge.target_id].add(edge.source_id)
    unvisited = set(adjacency)
    count = 0
    while unvisited:
        count += 1
        stack = [min(unvisited)]
        while stack:
            current = stack.pop()
            if current not in unvisited:
                continue
            unvisited.remove(current)
            stack.extend(sorted(adjacency[current] & unvisited, reverse=True))
    return count


def summarize_topology(snapshot: GraphSnapshot) -> TopologySummary:
    in_degree = {node.node_id: 0 for node in snapshot.nodes}
    out_degree = {node.node_id: 0 for node in snapshot.nodes}
    self_loop_count = 0
    relation_counts: dict[str, int] = {}
    for edge in snapshot.edges:
        out_degree[edge.source_id] += 1
        in_degree[edge.target_id] += 1
        if edge.source_id == edge.target_id:
            self_loop_count += 1
        relation_counts[edge.relation_type] = relation_counts.get(edge.relation_type, 0) + 1
    degrees = tuple(
        DegreeRecord(node_id=node_id, in_degree=in_degree[node_id], out_degree=out_degree[node_id])
        for node_id in sorted(in_degree)
    )
    isolated = tuple(value.node_id for value in degrees if value.total_degree == 0)
    payload = {
        'snapshot_id': snapshot.snapshot_id,
        'node_count': len(snapshot.nodes),
        'edge_count': len(snapshot.edges),
        'self_loop_count': self_loop_count,
        'weak_component_count': _weak_component_count(snapshot),
        'isolated_node_ids': list(isolated),
        'degrees': [value.to_dict() for value in degrees],
        'relation_counts': sorted(relation_counts.items()),
    }
    return TopologySummary(
        summary_id=deterministic_id('topology-summary', payload, length=24),
        snapshot_id=snapshot.snapshot_id,
        node_count=payload['node_count'],
        edge_count=payload['edge_count'],
        self_loop_count=self_loop_count,
        weak_component_count=payload['weak_component_count'],
        isolated_node_ids=isolated,
        degrees=degrees,
        relation_counts=tuple(sorted(relation_counts.items())),
    )


def compare_topology(before: TopologySummary, after: TopologySummary) -> TopologyDelta:
    before_degrees = before.degree_map()
    after_degrees = after.degree_map()
    degree_changes = tuple(
        DegreeChange(node_id, before_degrees.get(node_id), after_degrees.get(node_id))
        for node_id in sorted(set(before_degrees) | set(after_degrees))
        if before_degrees.get(node_id) != after_degrees.get(node_id)
    )
    before_relations = before.relation_count_map()
    after_relations = after.relation_count_map()
    relation_changes = tuple(
        RelationCountChange(
            relation_type,
            before_relations.get(relation_type, 0),
            after_relations.get(relation_type, 0),
        )
        for relation_type in sorted(set(before_relations) | set(after_relations))
        if before_relations.get(relation_type, 0) != after_relations.get(relation_type, 0)
    )
    before_isolated = set(before.isolated_node_ids)
    after_isolated = set(after.isolated_node_ids)
    payload = {
        'before_snapshot_id': before.snapshot_id,
        'after_snapshot_id': after.snapshot_id,
        'degree_changes': [value.to_dict() for value in degree_changes],
        'relation_count_changes': [value.to_dict() for value in relation_changes],
        'became_isolated': sorted(after_isolated - before_isolated),
        'no_longer_isolated': sorted(before_isolated - after_isolated),
    }
    return TopologyDelta(
        topology_delta_id=deterministic_id('topology-delta', payload, length=24),
        before_snapshot_id=before.snapshot_id,
        after_snapshot_id=after.snapshot_id,
        node_count_delta=after.node_count - before.node_count,
        edge_count_delta=after.edge_count - before.edge_count,
        self_loop_count_delta=after.self_loop_count - before.self_loop_count,
        weak_component_count_delta=after.weak_component_count - before.weak_component_count,
        degree_changes=degree_changes,
        relation_count_changes=relation_changes,
        became_isolated=tuple(sorted(after_isolated - before_isolated)),
        no_longer_isolated=tuple(sorted(before_isolated - after_isolated)),
    )
