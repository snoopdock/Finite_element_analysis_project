
"""G3 semantic graph analysis orchestration."""

from __future__ import annotations

from dataclasses import replace

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType, validate_query

from .context import SemanticContext
from .dependency import DependencyAnalyzer
from .helpers import make_analysis_id
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
        semantic_context: SemanticContext | None = None,
    ) -> None:
        self.graph = graph
        self.memory = memory if memory is not None else AuditWorkingMemory()
        self.semantic_context = semantic_context or SemanticContext()
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

        primitive_result = analyzer.analyze(query)
        result = replace(
            primitive_result,
            semantic_context=self.semantic_context,
            analysis_id=make_analysis_id(
                analysis_type=primitive_result.analysis_type,
                query_id=primitive_result.query_id,
                graph_fingerprint=primitive_result.graph_fingerprint,
                parameters=primitive_result.parameters,
                semantic_context=self.semantic_context,
            ),
        )
        self.memory.record(result)
        return result
