"""Lightweight query result contract.

G3 analysis normally returns :class:`GraphAnalysisResult`; this smaller result
remains useful for callers that only need a query-level projection.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GraphQueryResult:
    query_id: str
    entities: tuple[str, ...] = field(default_factory=tuple)
    relationships: tuple[str, ...] = field(default_factory=tuple)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "entities": list(self.entities),
            "relationships": list(self.relationships),
            "provenance": dict(self.provenance),
        }
