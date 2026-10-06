#!/usr/bin/env python3
"""Persistable semantic document model for the publication boundary.

This module models document organization, not scientific authority. Domain
objects such as equations, propositions, and sources are referenced by ID and
remain authoritative outside this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union
import uuid

from core.section_identity import (
    ensure_section_id,
    normalize_parent_ids,
)


SCHEMA_VERSION = 4


def _new_id() -> str:
    return str(uuid.uuid4())


class DocumentModelError(ValueError):
    """Raised when a document-model object violates its structural contract."""


@dataclass
class Text:
    """Free-form authorial text."""

    text: str

    type: str = field(init=False, default="text")

    def validate(self) -> None:
        if not isinstance(self.text, str):
            raise DocumentModelError("Text.text must be a string.")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {"type": self.type, "text": self.text}


@dataclass
class InlineMath:
    """Renderer-neutral inline mathematical content.

    Inline mathematics is presentation structure, not a domain equation.  It
    therefore carries the mathematical expression but no equation identity.
    Scientifically authoritative equations remain referenced through
    ``EquationOccurrence``.
    """

    expression: str

    type: str = field(init=False, default="inline_math")

    def validate(self) -> None:
        if not isinstance(self.expression, str) or not self.expression.strip():
            raise DocumentModelError("InlineMath.expression must be non-empty.")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {"type": self.type, "expression": self.expression}


@dataclass
class CitationOccurrence:
    """Inline reference to an authoritative evidence source."""

    source_id: str
    occurrence_id: str = field(default_factory=_new_id)

    type: str = field(init=False, default="citation_occurrence")

    def validate(self) -> None:
        if not self.occurrence_id.strip():
            raise DocumentModelError("Citation occurrence_id must be non-empty.")
        if not self.source_id.strip():
            raise DocumentModelError("Citation source_id must be non-empty.")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {
            "type": self.type,
            "occurrence_id": self.occurrence_id,
            "source_id": self.source_id,
        }


@dataclass
class CitationClusterOccurrence:
    """Inline citation occurrence that intentionally groups multiple sources.

    The cluster is a semantic publication object: source identities remain
    authoritative in the evidence registry, while ``occurrence_id`` identifies
    this specific grouped placement in the document.
    """

    source_ids: Tuple[str, ...]
    occurrence_id: str = field(default_factory=_new_id)

    type: str = field(init=False, default="citation_cluster_occurrence")

    def validate(self) -> None:
        if not isinstance(self.occurrence_id, str) or not self.occurrence_id.strip():
            raise DocumentModelError("Citation cluster occurrence_id must be non-empty.")
        if not isinstance(self.source_ids, tuple):
            raise DocumentModelError("Citation cluster source_ids must be a tuple.")
        if len(self.source_ids) < 2:
            raise DocumentModelError("Citation cluster must contain at least two source_ids.")
        if any(not isinstance(source_id, str) or not source_id.strip() for source_id in self.source_ids):
            raise DocumentModelError("Citation cluster source_ids must contain non-empty strings.")
        if len(set(self.source_ids)) != len(self.source_ids):
            raise DocumentModelError("Citation cluster source_ids must not contain duplicates.")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {
            "type": self.type,
            "occurrence_id": self.occurrence_id,
            "source_ids": list(self.source_ids),
        }


@dataclass
class CrossReferenceOccurrence:
    """Inline reference to another document object."""

    target_id: str
    occurrence_id: str = field(default_factory=_new_id)

    type: str = field(init=False, default="cross_reference_occurrence")

    def validate(self) -> None:
        if not self.occurrence_id.strip():
            raise DocumentModelError("Cross-reference occurrence_id must be non-empty.")
        if not self.target_id.strip():
            raise DocumentModelError("Cross-reference target_id must be non-empty.")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {
            "type": self.type,
            "occurrence_id": self.occurrence_id,
            "target_id": self.target_id,
        }


InlineNode = Union[Text, InlineMath, CitationOccurrence, CitationClusterOccurrence, CrossReferenceOccurrence]


@dataclass
class Paragraph:
    """A prose paragraph containing ordered inline content."""

    inline_content: List[InlineNode]

    type: str = field(init=False, default="paragraph")

    def validate(self) -> None:
        if not isinstance(self.inline_content, list):
            raise DocumentModelError("Paragraph.inline_content must be a list.")
        for node in self.inline_content:
            if not isinstance(
                node,
                (Text, InlineMath, CitationOccurrence, CitationClusterOccurrence, CrossReferenceOccurrence),
            ):
                raise DocumentModelError(
                    f"Unsupported paragraph inline node: {type(node).__name__}."
                )
            node.validate()

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {
            "type": self.type,
            "inline_content": [node.to_dict() for node in self.inline_content],
        }

    @classmethod
    def from_text(cls, text: str) -> "Paragraph":
        return cls(inline_content=[Text(text)])


@dataclass
class DisplayMath:
    """Renderer-neutral display mathematics without domain-object authority.

    This node exists for migration fidelity when legacy authoring contains a
    display expression that has not been promoted to an authoritative domain
    equation.  Once a domain equation is authorized, publication placement is
    represented by ``EquationOccurrence`` instead.
    """

    expression: str

    type: str = field(init=False, default="display_math")

    def validate(self) -> None:
        if not isinstance(self.expression, str) or not self.expression.strip():
            raise DocumentModelError("DisplayMath.expression must be non-empty.")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {"type": self.type, "expression": self.expression}


@dataclass
class EquationOccurrence:
    """A document placement of an authoritative semantic equation."""

    equation_id: str
    occurrence_id: str = field(default_factory=_new_id)
    label: Optional[str] = None
    caption: Optional[str] = None

    type: str = field(init=False, default="equation_occurrence")

    def validate(self) -> None:
        if not self.occurrence_id.strip():
            raise DocumentModelError("Equation occurrence_id must be non-empty.")
        if not self.equation_id.strip():
            raise DocumentModelError("Equation equation_id must be non-empty.")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        data = {
            "type": self.type,
            "occurrence_id": self.occurrence_id,
            "equation_id": self.equation_id,
        }
        if self.label is not None:
            data["label"] = self.label
        if self.caption is not None:
            data["caption"] = self.caption
        return data


@dataclass
class EquationProposal:
    """Non-authoritative candidate equation awaiting semantic verification."""

    proposal_id: str
    expression: str
    status: str = "proposed"
    explanation: Optional[str] = None
    role: Optional[str] = None

    type: str = field(init=False, default="equation_proposal")

    def validate(self) -> None:
        if not self.proposal_id.strip():
            raise DocumentModelError("Equation proposal_id must be non-empty.")
        if not self.expression.strip():
            raise DocumentModelError("Equation proposal expression must be non-empty.")
        if not self.status.strip():
            raise DocumentModelError("Equation proposal status must be non-empty.")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        data = {
            "type": self.type,
            "proposal_id": self.proposal_id,
            "expression": self.expression,
            "status": self.status,
        }
        if self.explanation is not None:
            data["explanation"] = self.explanation
        if self.role is not None:
            data["role"] = self.role
        return data


@dataclass
class EquationProposalReference:
    """Document placement of an unresolved, non-authoritative equation proposal."""

    proposal_id: str
    occurrence_id: str = field(default_factory=_new_id)

    type: str = field(init=False, default="equation_proposal_reference")

    def validate(self) -> None:
        if not self.occurrence_id.strip():
            raise DocumentModelError("Proposal reference occurrence_id must be non-empty.")
        if not self.proposal_id.strip():
            raise DocumentModelError("Proposal reference proposal_id must be non-empty.")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {
            "type": self.type,
            "occurrence_id": self.occurrence_id,
            "proposal_id": self.proposal_id,
        }


@dataclass
class Figure:
    """Structured figure placement metadata."""

    asset: str
    figure_id: str = field(default_factory=_new_id)
    caption: Optional[str] = None
    label: Optional[str] = None
    source_ids: List[str] = field(default_factory=list)

    type: str = field(init=False, default="figure")

    def validate(self) -> None:
        if not isinstance(self.figure_id, str) or not self.figure_id.strip():
            raise DocumentModelError("Figure figure_id must be non-empty.")
        if not isinstance(self.asset, str) or not self.asset.strip():
            raise DocumentModelError("Figure asset must be non-empty.")
        if self.caption is not None and not isinstance(self.caption, str):
            raise DocumentModelError("Figure caption must be a string or None.")
        if self.label is not None and not isinstance(self.label, str):
            raise DocumentModelError("Figure label must be a string or None.")
        if not isinstance(self.source_ids, list):
            raise DocumentModelError("Figure source_ids must be a list.")
        if any(not isinstance(source_id, str) or not source_id.strip() for source_id in self.source_ids):
            raise DocumentModelError("Figure source_ids must contain non-empty strings.")
        if len(set(self.source_ids)) != len(self.source_ids):
            raise DocumentModelError("Figure source_ids must not contain duplicates.")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        data = {
            "type": self.type,
            "figure_id": self.figure_id,
            "asset": self.asset,
            "source_ids": list(self.source_ids),
        }
        if self.caption is not None:
            data["caption"] = self.caption
        if self.label is not None:
            data["label"] = self.label
        return data


@dataclass
class Table:
    """Structured table placement metadata."""

    columns: List[Any]
    rows: List[List[Any]]
    table_id: str = field(default_factory=_new_id)
    caption: Optional[str] = None
    label: Optional[str] = None
    source_ids: List[str] = field(default_factory=list)

    type: str = field(init=False, default="table")

    def validate(self) -> None:
        if not isinstance(self.table_id, str) or not self.table_id.strip():
            raise DocumentModelError("Table table_id must be non-empty.")
        if not isinstance(self.columns, list) or not self.columns:
            raise DocumentModelError("Table columns must be a non-empty list.")
        if any(not isinstance(column, str) or not column.strip() for column in self.columns):
            raise DocumentModelError("Table columns must contain non-empty strings.")
        if not isinstance(self.rows, list) or not self.rows or any(not isinstance(row, list) for row in self.rows):
            raise DocumentModelError("Table rows must be a non-empty list of lists.")
        expected = len(self.columns)
        for row_index, row in enumerate(self.rows):
            if len(row) != expected:
                raise DocumentModelError(
                    f"Table row {row_index} has {len(row)} cells; expected {expected}."
                )
            if any(not isinstance(cell, str) for cell in row):
                raise DocumentModelError(
                    f"Table row {row_index} cells must all be strings."
                )
        if self.caption is not None and not isinstance(self.caption, str):
            raise DocumentModelError("Table caption must be a string or None.")
        if self.label is not None and not isinstance(self.label, str):
            raise DocumentModelError("Table label must be a string or None.")
        if not isinstance(self.source_ids, list):
            raise DocumentModelError("Table source_ids must be a list.")
        if any(not isinstance(source_id, str) or not source_id.strip() for source_id in self.source_ids):
            raise DocumentModelError("Table source_ids must contain non-empty strings.")
        if len(set(self.source_ids)) != len(self.source_ids):
            raise DocumentModelError("Table source_ids must not contain duplicates.")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        data = {
            "type": self.type,
            "table_id": self.table_id,
            "columns": list(self.columns),
            "rows": [list(row) for row in self.rows],
            "source_ids": list(self.source_ids),
        }
        if self.caption is not None:
            data["caption"] = self.caption
        if self.label is not None:
            data["label"] = self.label
        return data


@dataclass
class ConceptGraphNode:
    """Publication snapshot of one authoritative knowledge-graph concept.

    ``concept_id`` remains the authoritative graph UUID.  This document object
    only carries the minimal display payload required by publication.
    """

    concept_id: str
    name: str
    concept_type: str = "concept"

    type: str = field(init=False, default="concept_graph_node")

    def validate(self) -> None:
        try:
            uuid.UUID(str(self.concept_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise DocumentModelError("ConceptGraphNode concept_id must be a UUID string.") from exc
        if not isinstance(self.name, str) or not self.name.strip():
            raise DocumentModelError("ConceptGraphNode name must be non-empty.")
        if not isinstance(self.concept_type, str) or not self.concept_type.strip():
            raise DocumentModelError("ConceptGraphNode concept_type must be non-empty.")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {
            "type": self.type,
            "concept_id": self.concept_id,
            "name": self.name,
            "concept_type": self.concept_type,
        }


@dataclass
class ConceptGraphRelation:
    """Publication snapshot of one authoritative concept-to-concept relation."""

    relationship_id: str
    source_concept_id: str
    target_concept_id: str
    relation_type: str

    type: str = field(init=False, default="concept_graph_relation")

    def validate(self) -> None:
        for field_name, value in (
            ("relationship_id", self.relationship_id),
            ("source_concept_id", self.source_concept_id),
            ("target_concept_id", self.target_concept_id),
        ):
            try:
                uuid.UUID(str(value))
            except (ValueError, TypeError, AttributeError) as exc:
                raise DocumentModelError(
                    f"ConceptGraphRelation {field_name} must be a UUID string."
                ) from exc
        if self.source_concept_id == self.target_concept_id:
            raise DocumentModelError("ConceptGraphRelation cannot self-reference.")
        if not isinstance(self.relation_type, str) or not self.relation_type.strip():
            raise DocumentModelError("ConceptGraphRelation relation_type must be non-empty.")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {
            "type": self.type,
            "relationship_id": self.relationship_id,
            "source_concept_id": self.source_concept_id,
            "target_concept_id": self.target_concept_id,
            "relation_type": self.relation_type,
        }


@dataclass
class ConceptGraphView:
    """Non-authoritative publication view of the semantic knowledge graph.

    The view has its own occurrence UUID while preserving concept and
    relationship UUIDs from the authoritative graph. Any bounded selection is
    explicit metadata and must never be performed silently by a renderer.
    """

    nodes: List[ConceptGraphNode]
    relations: List[ConceptGraphRelation]
    occurrence_id: str = field(default_factory=_new_id)
    total_concepts: int = 0
    total_concept_relations: int = 0
    selection_policy: str = "all"

    type: str = field(init=False, default="concept_graph_view")

    def validate(self) -> None:
        try:
            uuid.UUID(str(self.occurrence_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise DocumentModelError("ConceptGraphView occurrence_id must be a UUID string.") from exc
        if not isinstance(self.nodes, list) or not self.nodes:
            raise DocumentModelError("ConceptGraphView nodes must be a non-empty list.")
        if not isinstance(self.relations, list):
            raise DocumentModelError("ConceptGraphView relations must be a list.")
        node_ids: Set[str] = set()
        for node in self.nodes:
            if not isinstance(node, ConceptGraphNode):
                raise DocumentModelError("ConceptGraphView nodes must be ConceptGraphNode objects.")
            node.validate()
            if node.concept_id in node_ids:
                raise DocumentModelError(f"Duplicate concept_id in ConceptGraphView: {node.concept_id}.")
            node_ids.add(node.concept_id)
        relation_ids: Set[str] = set()
        for relation in self.relations:
            if not isinstance(relation, ConceptGraphRelation):
                raise DocumentModelError("ConceptGraphView relations must be ConceptGraphRelation objects.")
            relation.validate()
            if relation.relationship_id in relation_ids:
                raise DocumentModelError(
                    f"Duplicate relationship_id in ConceptGraphView: {relation.relationship_id}."
                )
            relation_ids.add(relation.relationship_id)
            if relation.source_concept_id not in node_ids or relation.target_concept_id not in node_ids:
                raise DocumentModelError(
                    "ConceptGraphView relations must reference concepts included in the view."
                )
        if not isinstance(self.total_concepts, int) or self.total_concepts < len(self.nodes):
            raise DocumentModelError("ConceptGraphView total_concepts must cover all selected nodes.")
        if (
            not isinstance(self.total_concept_relations, int)
            or self.total_concept_relations < len(self.relations)
        ):
            raise DocumentModelError(
                "ConceptGraphView total_concept_relations must cover all selected relations."
            )
        if not isinstance(self.selection_policy, str) or not self.selection_policy.strip():
            raise DocumentModelError("ConceptGraphView selection_policy must be non-empty.")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {
            "type": self.type,
            "occurrence_id": self.occurrence_id,
            "nodes": [node.to_dict() for node in self.nodes],
            "relations": [relation.to_dict() for relation in self.relations],
            "total_concepts": self.total_concepts,
            "total_concept_relations": self.total_concept_relations,
            "selection_policy": self.selection_policy,
        }


@dataclass
class RelationshipTableRow:
    """Publication snapshot of one proposition-to-proposition relationship."""

    relationship_id: str
    source_proposition_id: str
    target_proposition_id: str
    source_statement: str
    relation_type: str
    target_statement: str

    type: str = field(init=False, default="relationship_table_row")

    def validate(self) -> None:
        for field_name, value in (
            ("relationship_id", self.relationship_id),
            ("source_proposition_id", self.source_proposition_id),
            ("target_proposition_id", self.target_proposition_id),
        ):
            try:
                uuid.UUID(str(value))
            except (ValueError, TypeError, AttributeError) as exc:
                raise DocumentModelError(
                    f"RelationshipTableRow {field_name} must be a UUID string."
                ) from exc
        for field_name, value in (
            ("source_statement", self.source_statement),
            ("relation_type", self.relation_type),
            ("target_statement", self.target_statement),
        ):
            if not isinstance(value, str) or not value.strip():
                raise DocumentModelError(f"RelationshipTableRow {field_name} must be non-empty.")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {
            "type": self.type,
            "relationship_id": self.relationship_id,
            "source_proposition_id": self.source_proposition_id,
            "target_proposition_id": self.target_proposition_id,
            "source_statement": self.source_statement,
            "relation_type": self.relation_type,
            "target_statement": self.target_statement,
        }


@dataclass
class RelationshipTableView:
    """Non-authoritative publication view of proposition relationships."""

    rows: List[RelationshipTableRow]
    occurrence_id: str = field(default_factory=_new_id)
    total_relationships: int = 0
    selection_policy: str = "all"

    type: str = field(init=False, default="relationship_table_view")

    def validate(self) -> None:
        try:
            uuid.UUID(str(self.occurrence_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise DocumentModelError("RelationshipTableView occurrence_id must be a UUID string.") from exc
        if not isinstance(self.rows, list) or not self.rows:
            raise DocumentModelError("RelationshipTableView rows must be a non-empty list.")
        seen: Set[str] = set()
        for row in self.rows:
            if not isinstance(row, RelationshipTableRow):
                raise DocumentModelError("RelationshipTableView rows must be RelationshipTableRow objects.")
            row.validate()
            if row.relationship_id in seen:
                raise DocumentModelError(
                    f"Duplicate relationship_id in RelationshipTableView: {row.relationship_id}."
                )
            seen.add(row.relationship_id)
        if not isinstance(self.total_relationships, int) or self.total_relationships < len(self.rows):
            raise DocumentModelError(
                "RelationshipTableView total_relationships must cover all selected rows."
            )
        if not isinstance(self.selection_policy, str) or not self.selection_policy.strip():
            raise DocumentModelError("RelationshipTableView selection_policy must be non-empty.")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {
            "type": self.type,
            "occurrence_id": self.occurrence_id,
            "rows": [row.to_dict() for row in self.rows],
            "total_relationships": self.total_relationships,
            "selection_policy": self.selection_policy,
        }


SectionChild = Union[
    Paragraph,
    DisplayMath,
    EquationOccurrence,
    EquationProposalReference,
    Figure,
    Table,
    ConceptGraphView,
    RelationshipTableView,
]


@dataclass
class Section:
    """Persisted document section with ordered children and lifecycle lineage."""

    title: str
    children: List[SectionChild]
    section_id: Optional[str] = None
    parent_section_ids: List[str] = field(default_factory=list)
    status: Optional[str] = None
    generated_from: Optional[str] = None
    subsection_index: Optional[int] = None

    type: str = field(init=False, default="section")

    def __post_init__(self) -> None:
        data = {"section_id": self.section_id} if self.section_id else {}
        ensure_section_id(data)
        self.section_id = data["section_id"]
        holder = {"parent_section_ids": list(self.parent_section_ids)}
        normalize_parent_ids(holder)
        self.parent_section_ids = holder["parent_section_ids"]

    def validate(self) -> None:
        if not self.section_id or not self.section_id.strip():
            raise DocumentModelError("Section section_id must be non-empty.")
        if not self.title.strip():
            raise DocumentModelError("Section title must be non-empty.")
        if not isinstance(self.children, list):
            raise DocumentModelError("Section.children must be a list.")
        for child in self.children:
            if not isinstance(
                child,
                (
                    Paragraph,
                    DisplayMath,
                    EquationOccurrence,
                    EquationProposalReference,
                    Figure,
                    Table,
                    ConceptGraphView,
                    RelationshipTableView,
                ),
            ):
                raise DocumentModelError(
                    f"Unsupported section child: {type(child).__name__}."
                )
            child.validate()
        if self.subsection_index is not None and self.subsection_index < 0:
            raise DocumentModelError("subsection_index must be non-negative.")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        data = {
            "type": self.type,
            "section_id": self.section_id,
            "title": self.title,
            "children": [child.to_dict() for child in self.children],
            "parent_section_ids": list(self.parent_section_ids),
        }
        for key, value in (
            ("status", self.status),
            ("generated_from", self.generated_from),
            ("subsection_index", self.subsection_index),
        ):
            if value is not None:
                data[key] = value
        return data


@dataclass
class Document:
    """Root persisted representation of publication structure."""

    children: List[Section]
    document_id: str = field(default_factory=_new_id)
    version: int = SCHEMA_VERSION
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_snapshot: Optional[Dict[str, Any]] = None

    type: str = field(init=False, default="document")

    def validate(self) -> None:
        if not self.document_id.strip():
            raise DocumentModelError("Document document_id must be non-empty.")
        if int(self.version) != SCHEMA_VERSION:
            raise DocumentModelError(
                f"Unsupported document schema version: {self.version}."
            )
        if not isinstance(self.children, list):
            raise DocumentModelError("Document.children must be a list.")
        section_ids: Set[str] = set()
        for section in self.children:
            if not isinstance(section, Section):
                raise DocumentModelError("Document.children may contain only sections.")
            section.validate()
            if section.section_id in section_ids:
                raise DocumentModelError(
                    f"Duplicate section_id in document: {section.section_id}."
                )
            section_ids.add(section.section_id)
        if not isinstance(self.metadata, dict):
            raise DocumentModelError("Document.metadata must be a dictionary.")
        if self.source_snapshot is not None and not isinstance(self.source_snapshot, dict):
            raise DocumentModelError("Document.source_snapshot must be a dictionary or None.")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        data = {
            "type": self.type,
            "document_id": self.document_id,
            "version": self.version,
            "children": [section.to_dict() for section in self.children],
            "metadata": dict(self.metadata),
        }
        if self.source_snapshot is not None:
            data["source_snapshot"] = dict(self.source_snapshot)
        return data



def document_from_legacy_sections(
    sections: Sequence[Dict[str, Any]],
    *,
    document_id: Optional[str] = None,
) -> Document:
    """Create a document model from legacy sections without changing their meaning.

    Legacy ``content`` is represented as one free-form paragraph. Existing
    section IDs and parent lineage are preserved. Equation/citation metadata is
    deliberately not reconstructed here; doing so would recreate the inference
    problem this model is intended to remove.
    """
    result: List[Section] = []
    for raw in sections or []:
        if not isinstance(raw, dict):
            continue
        section_id_holder = {"section_id": raw.get("section_id")}
        ensure_section_id(section_id_holder)
        parent_holder = {"parent_section_ids": raw.get("parent_section_ids", [])}
        normalize_parent_ids(parent_holder)

        content = raw.get("content", "")
        if not isinstance(content, str):
            content = str(content)

        children: List[SectionChild] = []
        if content.strip():
            children.append(Paragraph.from_text(content))

        result.append(
            Section(
                title=str(raw.get("title", "Untitled")),
                children=children,
                section_id=section_id_holder["section_id"],
                parent_section_ids=parent_holder["parent_section_ids"],
                status=raw.get("status"),
                generated_from=raw.get("generated_from"),
                subsection_index=raw.get("subsection_index"),
            )
        )

    return Document(children=result, document_id=document_id or _new_id())


def validate_document_references(
    document: Document,
    *,
    equation_ids: Optional[Set[str]] = None,
    source_ids: Optional[Set[str]] = None,
    target_ids: Optional[Set[str]] = None,
    proposal_ids: Optional[Set[str]] = None,
    renderable: bool = False,
) -> List[str]:
    """Return deterministic cross-object validation errors.

    The function never guesses a replacement identifier. Empty registries are
    treated as "registry not supplied" unless ``renderable=True``.
    """
    document.validate()
    errors: List[str] = []

    for section in document.children:
        for child in section.children:
            if isinstance(child, EquationOccurrence):
                if equation_ids is not None and child.equation_id not in equation_ids:
                    errors.append(
                        f"Section {section.section_id}: unknown equation_id {child.equation_id}."
                    )
            elif isinstance(child, EquationProposalReference):
                if proposal_ids is not None and child.proposal_id not in proposal_ids:
                    errors.append(
                        f"Section {section.section_id}: unknown proposal_id {child.proposal_id}."
                    )
                if renderable:
                    errors.append(
                        f"Section {section.section_id}: unresolved equation proposal "
                        f"{child.proposal_id} is not renderable."
                    )

            if isinstance(child, Figure):
                if source_ids is not None:
                    for source_id in child.source_ids:
                        if source_id not in source_ids:
                            errors.append(
                                f"Section {section.section_id}: unknown figure source_id {source_id}."
                            )
            elif isinstance(child, Table):
                if source_ids is not None:
                    for source_id in child.source_ids:
                        if source_id not in source_ids:
                            errors.append(
                                f"Section {section.section_id}: unknown table source_id {source_id}."
                            )

            if isinstance(child, Paragraph):
                for node in child.inline_content:
                    if isinstance(node, CitationOccurrence):
                        if source_ids is not None and node.source_id not in source_ids:
                            errors.append(
                                f"Section {section.section_id}: unknown citation source_id {node.source_id}."
                            )
                    elif isinstance(node, CitationClusterOccurrence):
                        if source_ids is not None:
                            for citation_source_id in node.source_ids:
                                if citation_source_id not in source_ids:
                                    errors.append(
                                        f"Section {section.section_id}: unknown citation source_id {citation_source_id}."
                                    )
                    elif isinstance(node, CrossReferenceOccurrence):
                        if target_ids is not None and node.target_id not in target_ids:
                            errors.append(
                                f"Section {section.section_id}: unknown cross-reference target_id {node.target_id}."
                            )

    return errors


def assert_renderable(
    document: Document,
    *,
    equation_ids: Set[str],
    source_ids: Set[str],
    target_ids: Set[str],
    proposal_ids: Optional[Set[str]] = None,
) -> None:
    """Raise ``DocumentModelError`` unless all renderability constraints pass."""
    errors = validate_document_references(
        document,
        equation_ids=equation_ids,
        source_ids=source_ids,
        target_ids=target_ids,
        proposal_ids=proposal_ids,
        renderable=True,
    )
    if errors:
        raise DocumentModelError("; ".join(errors))
