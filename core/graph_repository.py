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
    propositions = graph.setdefault("propositions", {})

    statement = proposition["statement"].strip().lower()
    source_signature = tuple(sorted(proposition.get("source_ids", [])))
    framework = proposition.get("framework", "").strip().lower()

    for proposition_id, existing in propositions.items():
        if not isinstance(existing, dict):
            continue
        if existing.get("statement", "").strip().lower() != statement:
            continue
        if tuple(sorted(existing.get("source_ids", []))) != source_signature:
            continue
        if existing.get("framework", "").strip().lower() != framework:
            continue
        proposition["proposition_id"] = str(proposition_id)
        propositions[str(proposition_id)] = proposition
        return str(proposition_id)

    proposition_id = proposition["proposition_id"]
    propositions[proposition_id] = proposition
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
    relationships = graph.setdefault("relationships", {})
    relation_type = str(relation_type).strip()

    for relationship_id, existing in relationships.items():
        if not isinstance(existing, dict):
            continue
        if str(existing.get("source_id")) != str(source_id):
            continue
        if str(existing.get("target_id")) != str(target_id):
            continue
        if str(existing.get("type")) != relation_type:
            continue
        # Refresh the evidence attached to an existing relationship while
        # retaining its stable relationship identity.
        existing["proposition_ids"] = list(proposition_ids or existing.get("proposition_ids", []))
        existing["source_ids"] = sorted(set(existing.get("source_ids", [])) | {str(v) for v in (source_ids or []) if v})
        existing["confidence"] = max(float(existing.get("confidence", 0.0)), float(confidence or 0.0))
        if framework:
            existing["framework"] = framework
        if assumptions:
            existing["assumptions"] = list(dict.fromkeys(existing.get("assumptions", []) + list(assumptions)))
        if conditions:
            existing["conditions"] = list(dict.fromkeys(existing.get("conditions", []) + list(conditions)))
        if reason:
            existing["reason"] = reason
        return str(relationship_id)

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

    relationships[relationship["relationship_id"]] = relationship
    violations = validate_graph_references(graph)
    if violations:
        relationships.pop(relationship["relationship_id"], None)
        return None
    return relationship["relationship_id"]
