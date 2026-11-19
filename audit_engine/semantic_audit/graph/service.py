
"""Stable public service boundary for semantic graph analysis."""

from __future__ import annotations

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph

from .analysis import (
    AuditWorkingMemory,
    GraphAnalysisEngine,
    GraphAnalysisResult,
    SemanticContext,
)
from .queries import GraphQuery


class SemanticGraphAnalysisService:
    """Facade shielding callers from analysis implementation details."""

    def __init__(
        self,
        graph: SemanticGraph,
        *,
        memory: AuditWorkingMemory | None = None,
        semantic_context: SemanticContext | None = None,
        traversal_backend: str = "reference",
        verify_backend_parity: bool = True,
    ) -> None:
        self.memory = memory if memory is not None else AuditWorkingMemory()
        self.engine = GraphAnalysisEngine(
            graph,
            memory=self.memory,
            semantic_context=semantic_context,
            traversal_backend=traversal_backend,
            verify_backend_parity=verify_backend_parity,
        )

    def analyze(self, query: GraphQuery) -> GraphAnalysisResult:
        return self.engine.execute(query)
