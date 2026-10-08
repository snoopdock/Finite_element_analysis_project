"""Versioned analysis result contract for G3 semantic graph analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .evidence import EvidenceRecord
from .models import AnalysisStatus, AnalysisType
from .observations import SemanticObservation


ANALYSIS_SCHEMA_VERSION = "semantic_graph_analysis/v1"


@dataclass(frozen=True)
class GraphAnalysisResult:
    analysis_id: str
    query_id: str
    analysis_type: AnalysisType
    status: AnalysisStatus
    algorithm: str
    graph_fingerprint: str
    source_entities: tuple[str, ...]
    discovered_entities: tuple[str, ...] = field(default_factory=tuple)
    observations: tuple[SemanticObservation, ...] = field(default_factory=tuple)
    evidence: tuple[EvidenceRecord, ...] = field(default_factory=tuple)
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = ANALYSIS_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        verification_counts: dict[str, int] = {}
        for record in self.evidence:
            key = record.verification_status.value
            verification_counts[key] = verification_counts.get(key, 0) + 1

        return {
            "schema_version": self.schema_version,
            "analysis_id": self.analysis_id,
            "query_id": self.query_id,
            "analysis_type": self.analysis_type.value,
            "status": self.status.value,
            "algorithm": self.algorithm,
            "graph_fingerprint": self.graph_fingerprint,
            "source_entities": list(self.source_entities),
            "discovered_entities": list(self.discovered_entities),
            "observations": [value.to_dict() for value in self.observations],
            "evidence": [value.to_dict() for value in self.evidence],
            "verification_summary": verification_counts,
            "parameters": dict(self.parameters),
            "metadata": dict(self.metadata),
        }
