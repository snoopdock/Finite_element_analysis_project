
"""G3 semantic graph analysis orchestration."""

from __future__ import annotations

from dataclasses import replace

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType, validate_query

from .context import SemanticContext
from .dependency import DependencyAnalyzer
from .helpers import make_analysis_id
from .impact import ImpactAnalyzer
from .memory import AuditWorkingMemory
from .path import PathAnalyzer
from .results import GraphAnalysisResult
from .structural import StructuralAnalyzer
from .traversal import GraphTraversalEngine


def _create_traversal_engine(
    graph: SemanticGraph,
    backend: str,
    *,
    verify_backend_parity: bool,
) -> GraphTraversalEngine:
    if backend == "reference":
        return GraphTraversalEngine(graph)
    if backend == "networkx":
        # Lazy import keeps the canonical semantic graph/query layer free of
        # eager third-party graph-library imports.
        from audit_engine.semantic_audit.graph.backend.networkx_traversal import (
            NetworkXGraphTraversalEngine,
        )
        return NetworkXGraphTraversalEngine(graph, verify_parity=verify_backend_parity)
    if backend in {"scipy", "igraph", "graph-tool", "snap"}:
        from audit_engine.semantic_audit.graph.backend.adapter_traversal import (
            NativeAdapterGraphTraversalEngine,
        )
        return NativeAdapterGraphTraversalEngine(
            graph, backend, verify_parity=verify_backend_parity,
        )
    raise ValueError(f"Unsupported semantic graph traversal backend: {backend!r}")


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
        traversal_backend: str = "reference",
        verify_backend_parity: bool = True,
    ) -> None:
        self.graph = graph
        self.memory = memory if memory is not None else AuditWorkingMemory()
        self.semantic_context = semantic_context or SemanticContext()
        self.traversal_backend = str(traversal_backend)
        self.traversal_engine = _create_traversal_engine(
            graph,
            self.traversal_backend,
            verify_backend_parity=verify_backend_parity,
        )
        self._analyzers = {
            QueryType.STRUCTURAL: StructuralAnalyzer(graph, traversal_engine=self.traversal_engine),
            QueryType.DEPENDENCY: DependencyAnalyzer(graph, traversal_engine=self.traversal_engine),
            QueryType.PATH: PathAnalyzer(graph, traversal_engine=self.traversal_engine),
            QueryType.IMPACT: ImpactAnalyzer(graph, traversal_engine=self.traversal_engine),
        }

    def execute(self, query: GraphQuery) -> GraphAnalysisResult:
        validate_query(query, self.graph)

        analyzer = self._analyzers.get(query.query_type)
        if analyzer is None:
            raise UnsupportedGraphQueryError(
                f"No G3 analyzer is registered for {query.query_type.value!r}."
            )

        primitive_result = analyzer.analyze(query)
        result_metadata = dict(primitive_result.metadata)
        result_metadata.update(self.traversal_engine.result_metadata())
        result = replace(
            primitive_result,
            metadata=result_metadata,
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
