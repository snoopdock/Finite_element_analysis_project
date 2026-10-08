"""Validation helpers for semantic graph queries."""

from __future__ import annotations

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph

from .models import GraphQuery, QueryType


class GraphQueryValidationError(ValueError):
    """Raised when a semantic query is invalid for the supplied graph."""


def validate_query(query: GraphQuery, graph: SemanticGraph) -> None:
    """Validate semantic identifiers and query-specific minimum structure."""

    if not query.source_entities:
        raise GraphQueryValidationError(
            "A semantic graph query requires at least one source entity."
        )

    missing = [
        entity_id
        for entity_id in query.source_entities
        if not graph.has_node(entity_id)
    ]
    if missing:
        raise GraphQueryValidationError(
            "Query references semantic node(s) absent from the graph: "
            + ", ".join(repr(value) for value in missing)
        )

    if query.query_type is QueryType.PATH:
        target = str(query.constraints.get("target_entity", "")).strip()
        if not target:
            raise GraphQueryValidationError(
                "PATH queries require constraints['target_entity']."
            )
        if not graph.has_node(target):
            raise GraphQueryValidationError(
                f"PATH target is absent from the graph: {target!r}"
            )
