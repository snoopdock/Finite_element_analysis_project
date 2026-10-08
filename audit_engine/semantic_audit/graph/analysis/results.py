from dataclasses import dataclass, field
from typing import Any


@dataclass
class GraphAnalysisResult:
    analysis_id: str
    analysis_type: str
    algorithm: str
    source_graph: str
    entities: list[str] = field(default_factory=list)
    relationships: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
