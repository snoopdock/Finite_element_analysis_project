#!/usr/bin/env python3
"""Identity and validation primitives for the provenance-aware knowledge graph."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Iterable, List, Optional

CONCEPT_ID_KEY = "concept_id"
PROPOSITION_ID_KEY = "proposition_id"
RELATIONSHIP_ID_KEY = "relationship_id"

VALID_CONCEPT_TYPES = {
    "concept",
    "method",
    "formulation",
    "theory",
    "application",
    "phenomenon",
    "parameter",
    "algorithm",
    "mathematical_object",
    "other",
}

VALID_PROPOSITION_STATUS = {
    "proposed",
    "supported",
    "conditionally_supported",
    "disputed",
    "insufficient_evidence",
    "superseded",
}

VALID_RELATIONSHIP_TYPES = {
    "parent_of",
    "subconcept_of",
    "specializes",
    "generalizes",
    "related_to",
    "alternative_to",
    "complements",
    "depends_on",
    "used_for",
    "extends",
    "contrasts_with",
    "appears_to_contradict",
    "contradicts_under_same_assumptions",
    "conditional_on",
    "supported_by",
    "disputed_by",
}


def new_graph_id() -> str:
    """Return a UUID4 string for a graph entity."""
    return str(uuid.uuid4())


def normalize_uuid(value: Any) -> Optional[str]:
    """Normalize a UUID-like value or return None."""
    try:
        return str(uuid.UUID(str(value).strip()))
    except (ValueError, AttributeError, TypeError):
        return None


def ensure_graph_id(entity: Dict[str, Any], key: str) -> str:
    """Ensure one graph entity has a stable UUID under ``key``."""
    current = normalize_uuid(entity.get(key))
    if current is None:
        current = new_graph_id()
    entity[key] = current
    return current


def normalize_id_list(values: Any) -> List[str]:
    """Normalize a collection of UUIDs while preserving order."""
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, Iterable) or isinstance(values, (bytes, bytearray)):
        return []

    result: List[str] = []
    seen = set()
    for value in values:
        normalized = normalize_uuid(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _normalize_opaque_list(values: Any) -> List[str]:
    """Normalize provenance/source identifiers without requiring UUID syntax."""
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    result = []
    seen = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def normalize_concept(concept: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize one concept record without inventing provenance."""
    ensure_graph_id(concept, CONCEPT_ID_KEY)
    concept["name"] = str(concept.get("name", "")).strip()
    concept["type"] = str(concept.get("type", "concept")).strip() or "concept"
    if concept["type"] not in VALID_CONCEPT_TYPES:
        concept["type"] = "other"
    concept["parent_concept_ids"] = normalize_id_list(
        concept.get("parent_concept_ids", [])
    )
    concept["aliases"] = [
        str(value).strip()
        for value in concept.get("aliases", [])
        if str(value).strip()
    ] if isinstance(concept.get("aliases", []), list) else []
    concept["source_ids"] = _normalize_opaque_list(concept.get("source_ids", []))
    concept["status"] = str(concept.get("status", "active")).strip() or "active"
    return concept


def normalize_proposition(proposition: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a proposition and keep claims separate from concepts."""
    ensure_graph_id(proposition, PROPOSITION_ID_KEY)
    proposition["concept_ids"] = normalize_id_list(proposition.get("concept_ids", []))
    proposition["statement"] = str(proposition.get("statement", "")).strip()
    proposition["framework"] = str(proposition.get("framework", "")).strip()
    proposition["assumptions"] = _normalize_strings(proposition.get("assumptions", []))
    proposition["conditions"] = _normalize_strings(proposition.get("conditions", []))
    proposition["domain_of_validity"] = _normalize_strings(
        proposition.get("domain_of_validity", [])
    )
    proposition["definitions"] = _normalize_strings(proposition.get("definitions", []))
    proposition["parameters"] = _normalize_strings(proposition.get("parameters", []))
    proposition["method"] = str(proposition.get("method", "")).strip()
    proposition["approximation"] = _normalize_strings(proposition.get("approximation", []))
    proposition["source_ids"] = _normalize_opaque_list(proposition.get("source_ids", []))
    status = str(proposition.get("status", "proposed")).strip()
    proposition["status"] = status if status in VALID_PROPOSITION_STATUS else "proposed"
    return proposition


def normalize_relationship(relationship: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a typed graph relationship."""
    ensure_graph_id(relationship, RELATIONSHIP_ID_KEY)
    relationship["source_id"] = normalize_uuid(relationship.get("source_id"))
    relationship["target_id"] = normalize_uuid(relationship.get("target_id"))
    relation_type = str(relationship.get("type", "related_to")).strip()
    relationship["type"] = (
        relation_type if relation_type in VALID_RELATIONSHIP_TYPES else "related_to"
    )
    relationship["proposition_ids"] = normalize_id_list(
        relationship.get("proposition_ids", [])
    )
    relationship["source_ids"] = _normalize_opaque_list(relationship.get("source_ids", []))
    relationship["framework"] = str(relationship.get("framework", "")).strip()
    relationship["assumptions"] = _normalize_strings(relationship.get("assumptions", []))
    relationship["conditions"] = _normalize_strings(relationship.get("conditions", []))
    relationship["confidence"] = _bounded_float(relationship.get("confidence", 0.0))
    relationship["status"] = str(relationship.get("status", "proposed")).strip() or "proposed"
    relationship["reason"] = str(relationship.get("reason", "")).strip()
    return relationship


def normalize_graph(graph: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize all graph collections in-place and return the graph."""
    concepts = graph.get("concepts", {})
    if isinstance(concepts, list):
        converted = {}
        for concept in concepts:
            if not isinstance(concept, dict):
                continue
            normalize_concept(concept)
            converted[concept[CONCEPT_ID_KEY]] = concept
        concepts = converted
    elif not isinstance(concepts, dict):
        concepts = {}

    for concept_id, concept in list(concepts.items()):
        if not isinstance(concept, dict):
            concepts.pop(concept_id, None)
            continue
        normalize_concept(concept)
        concepts.pop(concept_id, None)
        concepts[concept[CONCEPT_ID_KEY]] = concept

    propositions = graph.get("propositions", {})
    if isinstance(propositions, list):
        converted = {}
        for proposition in propositions:
            if not isinstance(proposition, dict):
                continue
            normalize_proposition(proposition)
            converted[proposition[PROPOSITION_ID_KEY]] = proposition
        propositions = converted
    elif not isinstance(propositions, dict):
        propositions = {}

    for proposition_id, proposition in list(propositions.items()):
        if not isinstance(proposition, dict):
            propositions.pop(proposition_id, None)
            continue
        normalize_proposition(proposition)
        propositions.pop(proposition_id, None)
        propositions[proposition[PROPOSITION_ID_KEY]] = proposition

    relationships = graph.get("relationships", {})
    if isinstance(relationships, list):
        converted = {}
        for relationship in relationships:
            if not isinstance(relationship, dict):
                continue
            normalize_relationship(relationship)
            converted[relationship[RELATIONSHIP_ID_KEY]] = relationship
        relationships = converted
    elif not isinstance(relationships, dict):
        relationships = {}

    for relationship_id, relationship in list(relationships.items()):
        if not isinstance(relationship, dict):
            relationships.pop(relationship_id, None)
            continue
        normalize_relationship(relationship)
        relationships.pop(relationship_id, None)
        relationships[relationship[RELATIONSHIP_ID_KEY]] = relationship

    graph["concepts"] = concepts
    graph["propositions"] = propositions
    graph["relationships"] = relationships
    graph.setdefault("concept_history", [])
    if not isinstance(graph["concept_history"], list):
        graph["concept_history"] = []
    return graph


def validate_graph_references(graph: Dict[str, Any]) -> List[str]:
    """Return deterministic graph-reference violations."""
    errors: List[str] = []
    concepts = graph.get("concepts", {}) if isinstance(graph, dict) else {}
    propositions = graph.get("propositions", {}) if isinstance(graph, dict) else {}
    relationships = graph.get("relationships", {}) if isinstance(graph, dict) else {}

    concept_ids = set(concepts) if isinstance(concepts, dict) else set()
    proposition_ids = set(propositions) if isinstance(propositions, dict) else set()

    for concept_id, concept in concepts.items() if isinstance(concepts, dict) else []:
        for parent_id in concept.get("parent_concept_ids", []):
            if parent_id == concept_id:
                errors.append(f"Concept {concept_id} cannot be its own parent.")
            elif parent_id not in concept_ids:
                errors.append(f"Concept {concept_id} references missing parent {parent_id}.")

    for proposition_id, proposition in propositions.items() if isinstance(propositions, dict) else []:
        for concept_id in proposition.get("concept_ids", []):
            if concept_id not in concept_ids:
                errors.append(f"Proposition {proposition_id} references missing concept {concept_id}.")

    for relationship_id, relationship in relationships.items() if isinstance(relationships, dict) else []:
        source_id = relationship.get("source_id")
        target_id = relationship.get("target_id")
        known_ids = concept_ids | proposition_ids
        if source_id not in known_ids:
            errors.append(f"Relationship {relationship_id} references missing source {source_id}.")
        if target_id not in known_ids:
            errors.append(f"Relationship {relationship_id} references missing target {target_id}.")
        for proposition_id in relationship.get("proposition_ids", []):
            if proposition_id not in proposition_ids:
                errors.append(
                    f"Relationship {relationship_id} references missing proposition {proposition_id}."
                )
    return errors


def _normalize_strings(values: Any) -> List[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    result = []
    seen = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _bounded_float(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0
