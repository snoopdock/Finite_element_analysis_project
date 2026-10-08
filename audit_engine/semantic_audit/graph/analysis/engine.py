"""G3 semantic graph analysis orchestration."""

from __future__ import annotations

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType, validate_query

from .dependency import DependencyAnalyzer
from .memory import AuditWorkingMemory
from .path import PathAnalyzer
from .results import GraphAnalysisResult
from .structural import StructuralAnalyzer


class UnsupportedGraphQueryError(ValueError):
    pass


class GraphAnalysisEngine:
    """Route validated semantic queries to bounded primitive analyzers."""

    def __init__(
        self,
        graph: SemanticGraph,
        *,
        memory: AuditWorkingMemory | None = None,
    ) -> None:
        self.graph = graph
        self.memory = memory if memory is not None else AuditWorkingMemory()
        self._analyzers = {
            QueryType.STRUCTURAL: StructuralAnalyzer(graph),
            QueryType.DEPENDENCY: DependencyAnalyzer(graph),
            QueryType.PATH: PathAnalyzer(graph),
        }

    def execute(self, query: GraphQuery) -> GraphAnalysisResult:
        validate_query(query, self.graph)

        analyzer = self._analyzers.get(query.query_type)
        if analyzer is None:
            raise UnsupportedGraphQueryError(
                f"No G3 analyzer is registered for {query.query_type.value!r}."
            )

        result = analyzer.analyze(query)
        self.memory.record(result)
        return result
