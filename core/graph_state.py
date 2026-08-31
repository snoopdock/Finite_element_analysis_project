#!/usr/bin/env python3
"""Non-destructive state adapter for provenance-aware scientific graph data."""

from __future__ import annotations

from typing import Any, Dict, List

from core.knowledge_graph import normalize_graph, validate_graph_references


def ensure_graph_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Return state with a normalized knowledge graph and deterministic diagnostics.

    The legacy ``knowledge_base`` remains untouched. The graph is a separate
    representation so concepts and propositions can evolve independently.
    """
    graph = state.get("knowledge_graph", {})
    if not isinstance(graph, dict):
        graph = {}

    normalize_graph(graph)
    state["knowledge_graph"] = graph
    state["knowledge_graph_violations"] = validate_graph_references(graph)
    return state


def empty_graph() -> Dict[str, Any]:
    """Return an empty graph container suitable for new state."""
    return {
        "concepts": {},
        "propositions": {},
        "relationships": {},
        "concept_history": [],
    }


def graph_summary(state: Dict[str, Any]) -> Dict[str, int]:
    """Return small, stable counts for reports and convergence diagnostics."""
    graph = ensure_graph_state(state).get("knowledge_graph", {})
    return {
        "concepts": len(graph.get("concepts", {})),
        "propositions": len(graph.get("propositions", {})),
        "relationships": len(graph.get("relationships", {})),
        "concept_history": len(graph.get("concept_history", [])),
        "violations": len(state.get("knowledge_graph_violations", [])),
    }
