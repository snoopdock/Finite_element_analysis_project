"""Shared, validated SemanticGraph projection data for optional native libraries.

The canonical SemanticGraph is never mutated. All adapters preserve directed
parallel edge *occurrences* and self-loops. Backend vertex numbers are not
semantic identities and are not stable across graph rebuilds.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from importlib.util import find_spec
from typing import Any

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph


class BackendUnavailableError(ImportError):
    """A requested optional native backend is missing or incompatible."""


INSTALLATION = {
    "igraph": "Install `python-igraph` (provides Python module `igraph`).",
    "graph-tool": "Install `graph-tool` in a compatible Linux/conda environment (module `graph_tool`).",
    "snap": "Install Stanford Snap.py (`snap-stanford`) for a supported Python/platform (module `snap`).",
}
MODULES = {"igraph": "igraph", "graph-tool": "graph_tool", "snap": "snap"}


def backend_available(name: str) -> bool:
    """Non-importing, best-effort discoverability; actual import is checked at use."""
    module = MODULES.get(name)
    if module is None:
        return False
    try:
        return find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def require_backend(name: str) -> Any:
    """Import only the requested optional dependency and give actionable errors."""
    import importlib

    try:
        module = importlib.import_module(MODULES[name])
    except (ImportError, OSError) as exc:
        raise BackendUnavailableError(f"Backend {name!r} is unavailable. {INSTALLATION[name]}") from exc
    if name == "snap" and not hasattr(module, "TNEANet"):
        raise BackendUnavailableError(
            "The installed module `snap` is not Stanford Snap.py or does not expose "
            "TNEANet; install the compatible `snap-stanford` distribution."
        )
    if name == "graph-tool" and not hasattr(module, "Graph"):
        raise BackendUnavailableError("The installed graph_tool module does not export Graph.")
    if name == "igraph" and not hasattr(module, "Graph"):
        raise BackendUnavailableError("The installed igraph module does not export Graph.")
    return module


@dataclass(frozen=True)
class ProjectionData:
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    node_to_index: dict[str, int]


def make_projection(graph: SemanticGraph) -> ProjectionData:
    """Copy and validate a complete snapshot BEFORE constructing native state.

    Rejects stale graphs edited directly through mutable ``nodes``/``edges``.
    SemanticGraph.add_* already checks invariants, but callers can bypass them.
    """
    if not isinstance(graph, SemanticGraph):
        raise TypeError("Expected the repository's canonical SemanticGraph")
    nodes = []
    by_id = {}
    for node in graph.nodes:
        ident = node.node_id
        if not isinstance(ident, str) or not ident.strip() or ident in by_id:
            raise ValueError("Invalid or duplicate semantic node identity")
        if not isinstance(node.entity_type, str) or not node.entity_type.strip():
            raise ValueError("Invalid semantic entity type")
        if not isinstance(node.attributes, dict) or not isinstance(node.metadata, dict):
            raise TypeError("Node attributes and metadata must be dictionaries")
        by_id[ident] = len(nodes)
        nodes.append({
            "id": ident, "type": node.entity_type,
            "attributes": deepcopy(node.attributes), "metadata": deepcopy(node.metadata),
        })
    edges = []
    for index, edge in enumerate(graph.edges):
        if edge.source_id not in by_id or edge.target_id not in by_id:
            raise ValueError("Dangling semantic graph edge")
        if not isinstance(edge.relation_type, str) or not edge.relation_type.strip():
            raise ValueError("Invalid semantic relationship type")
        if not isinstance(edge.attributes, dict) or not isinstance(edge.metadata, dict):
            raise TypeError("Edge attributes and metadata must be dictionaries")
        edges.append({
            "source": edge.source_id, "target": edge.target_id,
            "source_index": by_id[edge.source_id],
            "target_index": by_id[edge.target_id],
            "relation": edge.relation_type, "attributes": deepcopy(edge.attributes),
            "metadata": deepcopy(edge.metadata), "occurrence": index,
        })
    return ProjectionData(nodes, edges, by_id)


class NativeAdapterMixin:
    """Shared read API; all backends expose their actual graph via export()."""
    backend_name = ""

    def identity_mapping(self):
        return {
            "semantic_to_backend": dict(self._index),
            "backend_to_semantic": {v: k for k, v in self._index.items()},
            "semantic_edge_occurrence_to_backend": dict(self._edge_ids),
            "backend_to_semantic_edge_occurrence": {v: k for k, v in self._edge_ids.items()},
        }

    def nodes(self):
        return list(self._index)

    def edges(self):
        return [
            {"relation": e["relation"], "attributes": deepcopy(e["attributes"]),
             "metadata": deepcopy(e["metadata"])}
            for e in self._projection.edges
        ]

    def neighbors(self, node_id):
        if node_id not in self._index:
            raise KeyError(node_id)
        # NetworkX MultiDiGraph's neighbors are distinct outgoing neighbors.
        return list(dict.fromkeys(
            e["target"] for e in self._projection.edges if e["source"] == node_id
        ))

    def capabilities(self):
        return {
            "backend": self.backend_name, "directed_graph": True,
            "multiedges": True, "self_loops": True,
            "node_attributes": True, "edge_attributes": True,
            "metadata": True, "lossless": True,
            "semantic_ids_native": False,
            "snapshot_source_of_truth": "SemanticGraph",
        }

    def loss_report(self):
        return {
            "lossless": True,
            "lost": [],
            "transformed": ["semantic_node_ids_to_backend_integer_ids"],
        }

    def export(self):
        return self.graph

    def backend_graph(self):
        return self.graph
