"""Semantic graph query contracts.

Queries describe *intent*.  They intentionally contain no backend or
algorithm-specific state so callers do not become coupled to NetworkX,
SciPy, RDF stores, or future computational backends.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


class QueryType(str, Enum):
    """Supported semantic query categories for the G3 runtime."""

    STRUCTURAL = "structural"
    DEPENDENCY = "dependency"
    PATH = "path"


@dataclass(frozen=True)
class GraphQuery:
    """Backend-independent request for semantic graph analysis.

    ``source_entities`` are canonical semantic identifiers.  ``constraints``
    may refine the request, but must not encode backend implementation details.
    Concrete analyzers validate the constraints they understand.
    """

    query_id: str
    query_type: QueryType
    source_entities: tuple[str, ...] = field(default_factory=tuple)
    constraints: Mapping[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        query_id: str,
        query_type: QueryType,
        source_entities: Sequence[str] | None = None,
        constraints: Mapping[str, Any] | None = None,
    ) -> None:
        query_id = str(query_id).strip()
        if not query_id:
            raise ValueError("GraphQuery.query_id must be a non-empty string.")

        if not isinstance(query_type, QueryType):
            try:
                query_type = QueryType(query_type)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Unsupported query type: {query_type!r}") from exc

        normalized_sources = tuple(
            str(value).strip()
            for value in (source_entities or ())
            if str(value).strip()
        )

        object.__setattr__(self, "query_id", query_id)
        object.__setattr__(self, "query_type", query_type)
        object.__setattr__(self, "source_entities", normalized_sources)
        object.__setattr__(self, "constraints", dict(constraints or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "query_type": self.query_type.value,
            "source_entities": list(self.source_entities),
            "constraints": dict(self.constraints),
        }
