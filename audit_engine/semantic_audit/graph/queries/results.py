from dataclasses import dataclass, field
from typing import Any


@dataclass
class GraphQueryResult:
    query_id: str
    entities: list[str] = field(default_factory=list)
    relationships: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
