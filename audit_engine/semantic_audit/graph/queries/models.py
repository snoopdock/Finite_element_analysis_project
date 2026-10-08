from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class QueryType(Enum):
    STRUCTURAL = 'structural'
    DEPENDENCY = 'dependency'
    PATH = 'path'


@dataclass(frozen=True)
class GraphQuery:
    query_id: str
    query_type: QueryType
    source_entities: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)
