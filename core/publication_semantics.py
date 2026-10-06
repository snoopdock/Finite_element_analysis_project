#!/usr/bin/env python3
"""Semantic publication views derived from the authoritative knowledge graph.

The knowledge graph remains authoritative for concept/proposition/relationship
identity.  This module creates explicit, non-authoritative document objects for
publication.  Selection policy lives here rather than in a renderer so bounded
views are observable and never silently truncated by LaTeX code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
import uuid

from core.document_model import (
    ConceptGraphNode,
    ConceptGraphRelation,
    ConceptGraphView,
    RelationshipTableRow,
    RelationshipTableView,
    Section,
)

_PUBLICATION_VIEW_NAMESPACE = uuid.UUID("69c869b8-4ec6-493d-943e-a69ac41cc57c")

# Publication bounds are projection policy, not graph-capacity limits. The
# authoritative graph may grow without changing its UUID identity model.
MAX_CONCEPT_GRAPH_NODES = 12
MAX_RELATIONSHIP_TABLE_ROWS = 20
CONCEPT_SELECTION_POLICY = "stable_graph_insertion_order_prefix"
RELATIONSHIP_SELECTION_POLICY = "stable_graph_insertion_order_prefix"


@dataclass(frozen=True)
class PublicationGraphSections:
    """Optional semantic sections and a deterministic diagnostic report."""

    conceptual_map: Section | None
    relationship_table: Section | None
    report: dict[str, Any]


def _view_uuid(document_id: str, purpose: str) -> str:
    return str(uuid.uuid5(_PUBLICATION_VIEW_NAMESPACE, f"{document_id}:{purpose}"))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def build_publication_graph_sections(
    knowledge_graph: Mapping[str, Any] | None,
    *,
    document_id: str,
    max_concepts: int = MAX_CONCEPT_GRAPH_NODES,
    max_relationship_rows: int = MAX_RELATIONSHIP_TABLE_ROWS,
) -> PublicationGraphSections:
    """Create explicit publication snapshots from the authoritative graph.

    The graph itself is never mutated. Concepts and relationships preserve their
    authoritative UUIDs. The publication view/section identities are stable
    UUID5 values derived from the semantic document identity.
    """
    graph = _mapping(knowledge_graph)
    concepts = _mapping(graph.get("concepts"))
    propositions = _mapping(graph.get("propositions"))
    relationships = _mapping(graph.get("relationships"))

    selected_concept_items = list(concepts.items())[: max(0, int(max_concepts))]
    selected_concept_ids = {str(concept_id) for concept_id, _ in selected_concept_items}
    nodes: list[ConceptGraphNode] = []
    for concept_id, raw in selected_concept_items:
        concept = _mapping(raw)
        nodes.append(
            ConceptGraphNode(
                concept_id=str(concept_id),
                name=str(concept.get("name", "Unnamed concept")),
                concept_type=str(concept.get("type", "concept") or "concept"),
            )
        )

    all_concept_relations = []
    for relationship_id, raw in relationships.items():
        relationship = _mapping(raw)
        source_id = str(relationship.get("source_id") or "")
        target_id = str(relationship.get("target_id") or "")
        if source_id in concepts and target_id in concepts:
            all_concept_relations.append((relationship_id, relationship))

    selected_relations: list[ConceptGraphRelation] = []
    for relationship_id, relationship in all_concept_relations:
        source_id = str(relationship.get("source_id") or "")
        target_id = str(relationship.get("target_id") or "")
        if source_id not in selected_concept_ids or target_id not in selected_concept_ids:
            continue
        selected_relations.append(
            ConceptGraphRelation(
                relationship_id=str(relationship_id),
                source_concept_id=source_id,
                target_concept_id=target_id,
                relation_type=str(relationship.get("type", "related_to") or "related_to"),
            )
        )

    conceptual_map: Section | None = None
    if nodes:
        view = ConceptGraphView(
            occurrence_id=_view_uuid(document_id, "concept-graph-view"),
            nodes=nodes,
            relations=selected_relations,
            total_concepts=len(concepts),
            total_concept_relations=len(all_concept_relations),
            selection_policy=(
                "all" if len(nodes) == len(concepts) else CONCEPT_SELECTION_POLICY
            ),
        )
        conceptual_map = Section(
            section_id=_view_uuid(document_id, "conceptual-map-section"),
            title="Conceptual Map",
            children=[view],
            status="publication_view",
            generated_from="knowledge_graph",
        )

    proposition_rows: list[RelationshipTableRow] = []
    all_proposition_relations = []
    for relationship_id, raw in relationships.items():
        relationship = _mapping(raw)
        source_id = str(relationship.get("source_id") or "")
        target_id = str(relationship.get("target_id") or "")
        if source_id not in propositions or target_id not in propositions:
            continue
        source = _mapping(propositions[source_id])
        target = _mapping(propositions[target_id])
        if not str(source.get("statement", "")).strip() or not str(target.get("statement", "")).strip():
            continue
        all_proposition_relations.append((relationship_id, relationship, source, target))

    for relationship_id, relationship, source, target in all_proposition_relations[
        : max(0, int(max_relationship_rows))
    ]:
        proposition_rows.append(
            RelationshipTableRow(
                relationship_id=str(relationship_id),
                source_proposition_id=str(relationship.get("source_id")),
                target_proposition_id=str(relationship.get("target_id")),
                source_statement=str(source.get("statement", "")),
                relation_type=str(relationship.get("type", "related_to") or "related_to"),
                target_statement=str(target.get("statement", "")),
            )
        )

    relationship_table: Section | None = None
    if proposition_rows:
        view = RelationshipTableView(
            occurrence_id=_view_uuid(document_id, "relationship-table-view"),
            rows=proposition_rows,
            total_relationships=len(all_proposition_relations),
            selection_policy=(
                "all"
                if len(proposition_rows) == len(all_proposition_relations)
                else RELATIONSHIP_SELECTION_POLICY
            ),
        )
        relationship_table = Section(
            section_id=_view_uuid(document_id, "scientific-relationships-section"),
            title="Scientific Perspectives and Relationships",
            children=[view],
            status="publication_view",
            generated_from="knowledge_graph",
        )

    report = {
        "concept_graph": {
            "available_concepts": len(concepts),
            "selected_concepts": len(nodes),
            "available_concept_relations": len(all_concept_relations),
            "selected_concept_relations": len(selected_relations),
            "selection_policy": (
                "all" if len(nodes) == len(concepts) else CONCEPT_SELECTION_POLICY
            ),
        },
        "relationship_table": {
            "available_relationships": len(all_proposition_relations),
            "selected_relationships": len(proposition_rows),
            "selection_policy": (
                "all"
                if len(proposition_rows) == len(all_proposition_relations)
                else RELATIONSHIP_SELECTION_POLICY
            ),
        },
    }
    return PublicationGraphSections(
        conceptual_map=conceptual_map,
        relationship_table=relationship_table,
        report=report,
    )
