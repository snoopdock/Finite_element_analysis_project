from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class SourceLocation:
    file: str
    line: int


@dataclass
class DependencyEdge:
    source: str
    target: str
    kind: str
    location: SourceLocation


@dataclass
class SymbolReference:
    file: str
    symbol: str
    module: str
    line: int
    usage: str

    # New fields
    classification: str = "UNKNOWN"
    classification_reason: str = ""


@dataclass
class AuditInventory:
    python_files: List[str] = field(default_factory=list)

    dependencies: List[DependencyEdge] = field(
        default_factory=list
    )

    symbols: List[SymbolReference] = field(
        default_factory=list
    )

    metadata: Dict = field(
        default_factory=dict
    )
