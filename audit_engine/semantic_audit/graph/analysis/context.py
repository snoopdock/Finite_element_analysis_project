
"""Versioned semantic interpretation context for graph analysis artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .identity import deterministic_id


SEMANTIC_CONTEXT_SCHEMA_VERSION = "semantic_context/v1"


@dataclass(frozen=True)
class SemanticContext:
    """Identify the semantic contracts under which a graph was interpreted.

    A graph content fingerprint alone is insufficient to reproduce meaning:
    identical nodes and edges may be interpreted differently when the graph
    schema, relationship vocabulary, projection contract, or analysis contract
    changes.  ``projection_contract_version`` is optional because some graphs
    are constructed directly rather than projected from another representation.
    """

    graph_schema_version: str = "semantic_graph/v1"
    relationship_vocabulary_version: str = "open-vocabulary/v1"
    projection_contract_version: str | None = None
    analysis_contract_version: str = "semantic_graph_analysis_contract/v2"
    schema_version: str = SEMANTIC_CONTEXT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        required = {
            "graph_schema_version": self.graph_schema_version,
            "relationship_vocabulary_version": self.relationship_vocabulary_version,
            "analysis_contract_version": self.analysis_contract_version,
            "schema_version": self.schema_version,
        }
        for name, value in required.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"SemanticContext.{name} must be a non-empty string.")
        if self.projection_contract_version is not None:
            if not isinstance(self.projection_contract_version, str) or not self.projection_contract_version.strip():
                raise ValueError(
                    "SemanticContext.projection_contract_version must be None or a non-empty string."
                )

    @property
    def fingerprint(self) -> str:
        return deterministic_id("semantic-context", self.to_dict(), length=24)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "graph_schema_version": self.graph_schema_version,
            "relationship_vocabulary_version": self.relationship_vocabulary_version,
            "projection_contract_version": self.projection_contract_version,
            "analysis_contract_version": self.analysis_contract_version,
        }
