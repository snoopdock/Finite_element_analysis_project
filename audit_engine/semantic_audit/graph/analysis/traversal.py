"""Deterministic traversal over the canonical SemanticGraph.

This module is a small reference implementation.  It does not import any graph
backend.  Optimized backends may later implement the same semantic contract,
with this implementation serving as a correctness oracle for contract tests.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable

from audit_engine.semantic_audit.core.semantic_graph import (
    SemanticEdge,
    SemanticGraph,
)

from .evidence import EvidenceRecord
from .identity import edge_fingerprint, graph_fingerprint
from .models import TraversalDirection


@dataclass(frozen=True)
class TraversalStep:
    source_id: str
    target_id: str
    relation_type: str
    traversed_from: str
    traversed_to: str
    evidence_id: str
    depth: int

    def to_dict(self) -> dict[str, str]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type,
            "traversed_from": self.traversed_from,
            "traversed_to": self.traversed_to,
            "evidence_id": self.evidence_id,
            "depth": self.depth,
        }


@dataclass(frozen=True)
class TraversalHit:
    node_id: str
    depth: int
    path: tuple[TraversalStep, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "depth": self.depth,
            "path": [step.to_dict() for step in self.path],
        }


@dataclass(frozen=True)
class TraversalResult:
    start_node: str
    direction: TraversalDirection
    graph_fingerprint: str
    hits: tuple[TraversalHit, ...] = field(default_factory=tuple)
    steps: tuple[TraversalStep, ...] = field(default_factory=tuple)
    evidence: tuple[EvidenceRecord, ...] = field(default_factory=tuple)
    truncated: bool = False
    stop_reason: str | None = None
    examined_edges: int = 0

    @property
    def visited_nodes(self) -> tuple[str, ...]:
        return tuple(hit.node_id for hit in self.hits)


class GraphTraversalError(ValueError):
    pass


class GraphTraversalEngine:
    """Cycle-safe deterministic breadth-first traversal."""

    ALGORITHM = "deterministic_breadth_first_search"

    def __init__(self, graph: SemanticGraph):
        self.graph = graph

    def _candidate_edges(
        self,
        node_id: str,
        *,
        direction: TraversalDirection,
        relation_types: set[str] | None,
        outgoing: dict[str, list[SemanticEdge]],
        incoming: dict[str, list[SemanticEdge]],
    ) -> list[tuple[SemanticEdge, str]]:
        candidates: list[tuple[SemanticEdge, str]] = []
        if direction in (TraversalDirection.OUTGOING, TraversalDirection.BOTH):
            candidates.extend((edge, edge.target_id) for edge in outgoing.get(node_id, [])
                              if relation_types is None or edge.relation_type in relation_types)
        if direction in (TraversalDirection.INCOMING, TraversalDirection.BOTH):
            candidates.extend((edge, edge.source_id) for edge in incoming.get(node_id, [])
                              if relation_types is None or edge.relation_type in relation_types)
        candidates.sort(
            key=lambda item: (
                item[1], item[0].relation_type, item[0].source_id,
                item[0].target_id, edge_fingerprint(item[0]),
            )
        )
        return candidates

    def walk(
        self,
        start_node: str,
        *,
        direction: TraversalDirection = TraversalDirection.OUTGOING,
        relation_types: Iterable[str] | None = None,
        max_depth: int | None = 1,
        max_visited_nodes: int | None = None,
        max_steps: int | None = None,
    ) -> TraversalResult:
        if not self.graph.has_node(start_node):
            raise GraphTraversalError(
                f"Traversal start node is absent from graph: {start_node!r}"
            )
        if max_depth is not None and max_depth < 0:
            raise GraphTraversalError("max_depth must be non-negative or None.")
        if max_visited_nodes is not None and (
            isinstance(max_visited_nodes, bool) or not isinstance(max_visited_nodes, int) or max_visited_nodes < 1
        ):
            raise GraphTraversalError("max_visited_nodes must be a positive integer or None.")
        if max_steps is not None and (
            isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 1
        ):
            raise GraphTraversalError("max_steps must be a positive integer or None.")

        # Build adjacency once per walk. The previous implementation scanned the
        # complete edge list for every visited node, making broad queries O(V*E).
        outgoing: dict[str, list[SemanticEdge]] = {}
        incoming: dict[str, list[SemanticEdge]] = {}
        for edge in self.graph.edges:
            outgoing.setdefault(edge.source_id, []).append(edge)
            incoming.setdefault(edge.target_id, []).append(edge)
        for values in (*outgoing.values(), *incoming.values()):
            values.sort(key=lambda edge: (edge.target_id, edge.relation_type, edge.source_id, edge_fingerprint(edge)))

        normalized_relations = None
        if relation_types is not None:
            normalized_relations = {
                str(value).strip()
                for value in relation_types
                if str(value).strip()
            }

        queue = deque([(start_node, 0, tuple())])
        visited = {start_node}
        hits: list[TraversalHit] = []
        steps: list[TraversalStep] = []
        evidence_by_id: dict[str, EvidenceRecord] = {}

        truncated = False
        stop_reason: str | None = None
        examined_edges = 0
        stop = False
        while queue and not stop:
            current, depth, path = queue.popleft()
            if max_depth is not None and depth >= max_depth:
                continue

            for edge, neighbor in self._candidate_edges(
                current,
                direction=direction,
                relation_types=normalized_relations,
                outgoing=outgoing,
                incoming=incoming,
            ):
                if max_steps is not None and examined_edges >= max_steps:
                    truncated = True
                    stop_reason = "max_traversal_steps"
                    stop = True
                    break
                examined_edges += 1
                evidence = EvidenceRecord.from_edge(edge)
                evidence_by_id[evidence.evidence_id] = evidence

                step = TraversalStep(
                    source_id=edge.source_id,
                    target_id=edge.target_id,
                    relation_type=edge.relation_type,
                    traversed_from=current,
                    traversed_to=neighbor,
                    evidence_id=evidence.evidence_id,
                    depth=depth + 1,
                )
                steps.append(step)

                if neighbor in visited:
                    continue
                if max_visited_nodes is not None and len(visited) >= max_visited_nodes:
                    truncated = True
                    stop_reason = "max_visited_nodes"
                    stop = True
                    break

                visited.add(neighbor)
                next_path = path + (step,)
                hit = TraversalHit(
                    node_id=neighbor,
                    depth=depth + 1,
                    path=next_path,
                )
                hits.append(hit)
                queue.append((neighbor, depth + 1, next_path))

        hits.sort(key=lambda hit: (hit.depth, hit.node_id))
        evidence = tuple(
            evidence_by_id[key]
            for key in sorted(evidence_by_id)
        )

        return TraversalResult(
            start_node=start_node,
            direction=direction,
            graph_fingerprint=graph_fingerprint(self.graph),
            hits=tuple(hits),
            steps=tuple(steps),
            evidence=evidence,
            truncated=truncated,
            stop_reason=stop_reason,
            examined_edges=examined_edges,
        )
