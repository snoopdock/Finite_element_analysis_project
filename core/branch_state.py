#!/usr/bin/env python3
"""Derived, non-authoritative concept-branch state for reporting."""

from __future__ import annotations

from typing import Any, Dict

from core.concept_branches import concept_branches


def refresh_branch_view(state: Dict[str, Any]) -> Dict[str, Any]:
    """Store the current explicit hierarchy as a derived state view."""
    graph = state.get("knowledge_graph", {}) if isinstance(state, dict) else {}
    view = concept_branches(graph)
    state["concept_branch_view"] = view
    return view
