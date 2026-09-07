from dataclasses import dataclass, field
from typing import List


@dataclass
class ImportReference:

    file: str
    line: int

    module: str

    imported_symbols: List[str] = field(
        default_factory=list
    )


@dataclass
class SymbolUsage:

    file: str

    line: int

    symbol: str

    module: str

    usage_type: str


@dataclass
class SemanticFinding:

    file: str

    module: str

    symbol: str

    classification: str

    reason: str


@dataclass
class AuditReport:

    imports: List[ImportReference] = field(
        default_factory=list
    )

    symbols: List[SymbolUsage] = field(
        default_factory=list
    )

    findings: List[SemanticFinding] = field(
        default_factory=list
    )
