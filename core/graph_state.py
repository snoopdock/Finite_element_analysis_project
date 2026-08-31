#!/usr/bin/env python3
"""Non-destructive state adapter for provenance-aware scientific graph data."""

from __future__ import annotations

from typing import Any, Dict

from core.knowledge_graph_builder import sync_legacy_knowledge_base
from core.concept_linking import candidate_concept_links
from core.graph_membership import apply_explicit_membership
from core.proposition_history import record_proposition_history
from core.knowledge_graph import normalize_graph, validate_graph_references


def ensure_graph_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure the graph is normalized and populated from legacy KB data."""
    graph = state.get("knowledge_graph", {})
    if not isinstance(graph, dict):
        graph = {}
    state["knowledge_graph"] = graph

    sync_legacy_knowledge_base(state)
    normalize_graph(state["knowledge_graph"])
    candidate_concept_links(state["knowledge_graph"])
    apply_explicit_membership(state)
    normalize_graph(state["knowledge_graph"])
    record_proposition_history(state)
    state["knowledge_graph_violations"] = validate_graph_references(
        state["knowledge_graph"]
    )
    return state


def empty_graph() -> Dict[str, Any]:
    """Return an empty graph container suitable for new state."""
    return {
        "concepts": {},
        "propositions": {},
        "relationships": {},
        "concept_history": [],
        "proposition_history": [],
    }


def graph_summary(state: Dict[str, Any]) -> Dict[str, int]:
    """Return small, stable counts for reports and convergence diagnostics."""
    graph = ensure_graph_state(state).get("knowledge_graph", {})
    return {
        "concepts": len(graph.get("concepts", {})),
        "propositions": len(graph.get("propositions", {})),
        "relationships": len(graph.get("relationships", {})),
        "concept_history": len(graph.get("concept_history", [])),
        "proposition_history": len(graph.get("proposition_history", [])),
        "violations": len(state.get("knowledge_graph_violations", [])),
    }
