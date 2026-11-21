"""Backend-neutral contract for semantic graph projections and native adjacency.

The canonical SemanticGraph remains authoritative. Projection inspection is a
full-graph audit operation; iter_adjacent_edge_occurrences is the query-time
operation and must use the selected library's native local adjacency API.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from audit_engine.semantic_audit.graph.analysis.models import TraversalDirection


@dataclass(frozen=True)
class NativeNodeRecord:
    """Canonical semantic node recovered from a native projection."""
    node_id: str
    entity_type: str
    attributes: Mapping[str, Any]
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class NativeEdgeOccurrence:
    """One snapshot-scoped canonical edge occurrence, including parallel edges."""
    occurrence_id: int
    source_id: str
    target_id: str
    relation_type: str
    attributes: Mapping[str, Any]
    metadata: Mapping[str, Any]
    backend_edge_ref: Any = None


class NativeAdjacencyNotSupportedError(NotImplementedError):
    """The adapter has not implemented native per-node edge-occurrence access."""


class SemanticGraphAdapter(ABC):
    """Typed contract for computational projections of SemanticGraph.

    Existing adapters remain constructible while they are migrated: the two
    full-projection iterators and local adjacency method have explicit default
    failures rather than silently emulating a native query with a Python scan.
    """

    @abstractmethod
    def export(self) -> Any:
        """Return the backend-specific projection."""

    @abstractmethod
    def capabilities(self) -> dict[str, Any]:
        """Describe representation properties; this is not acceptance evidence."""

    @abstractmethod
    def identity_mapping(self) -> dict[str, Any]:
        """Return semantic/native node and edge-occurrence identity mappings."""

    @abstractmethod
    def loss_report(self) -> dict[str, Any]:
        """Describe information preserved, transformed, or lost."""

    def iter_native_nodes(self) -> Iterable[NativeNodeRecord]:
        """Enumerate all native nodes for explicit projection validation only."""
        raise NativeAdjacencyNotSupportedError(
            f"{type(self).__name__} does not implement native node inspection"
        )

    def iter_native_edge_occurrences(self) -> Iterable[NativeEdgeOccurrence]:
        """Enumerate all native edge occurrences for explicit projection validation."""
        raise NativeAdjacencyNotSupportedError(
            f"{type(self).__name__} does not implement native edge inspection"
        )

    def iter_adjacent_edge_occurrences(
        self, node_id: str, direction: TraversalDirection
    ) -> Iterable[NativeEdgeOccurrence]:
        """Return exact incident occurrences using native local adjacency.

        BOTH returns the union of incoming and outgoing occurrences. A self-loop
        is one occurrence and is returned once. Unknown semantic IDs raise
        KeyError; a known isolated node returns an empty iterable.
        """
        raise NativeAdjacencyNotSupportedError(
            f"{type(self).__name__} does not implement native local adjacency"
        )
