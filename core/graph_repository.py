#!/usr/bin/env python3
"""Validated operations for the provenance-aware scientific knowledge graph."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from core.knowledge_graph import (
    new_graph_id,
    normalize_concept,
    normalize_proposition,
    normalize_relationship,
    validate_graph_references,
)


def upsert_concept(graph: Dict[str, Any], concept: Dict[str, Any]) -> str:
    normalize_concept(concept)
    concept_id = concept["concept_id"]
    graph.setdefault("concepts", {})[concept_id] = concept
    return concept_id


def upsert_proposition(graph: Dict[str, Any], proposition: Dict[str, Any]) -> str:
    normalize_proposition(proposition)
    proposition_id = proposition["proposition_id"]
    graph.setdefault("propositions", {})[proposition_id] = proposition
    return proposition_id


def upsert_relationship(
    graph: Dict[str, Any],
    *,
    source_id: str,
    target_id: str,
    relation_type: str,
    proposition_ids: Optional[Iterable[str]] = None,
    source_ids: Optional[Iterable[str]] = None,
    confidence: float = 0.0,
    framework: str = "",
    assumptions: Optional[Iterable[str]] = None,
    conditions: Optional[Iterable[str]] = None,
    reason: str = "",
) -> Optional[str]:
    relationship = normalize_relationship({
        "relationship_id": new_graph_id(),
        "source_id": source_id,
        "target_id": target_id,
        "type": relation_type,
        "proposition_ids": list(proposition_ids or []),
        "source_ids": list(source_ids or []),
        "confidence": confidence,
        "framework": framework,
        "assumptions": list(assumptions or []),
        "conditions": list(conditions or []),
        "reason": reason,
    })

    graph.setdefault("relationships", {})[relationship["relationship_id"]] = relationship
    violations = validate_graph_references(graph)
    if violations:
        graph["relationships"].pop(relationship["relationship_id"], None)
        return None
    return relationship["relationship_id"]
