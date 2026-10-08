"""Dependency analysis over typed semantic relationships."""

from __future__ import annotations

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph
from audit_engine.semantic_audit.graph.queries.models import GraphQuery, QueryType

from .helpers import (
    make_analysis_id,
    observations_from_traversal,
    parse_direction,
    parse_max_depth,
    parse_relation_types,
)
from .models import AnalysisStatus, AnalysisType
from .results import GraphAnalysisResult
from .traversal import GraphTraversalEngine


class DependencyAnalyzer:
    """Discover direct or transitive dependency structure.

    The analyzer reports graph observations only.  It does not determine
    whether a dependency is permitted, dangerous, or architecturally valid.
    """

    DEFAULT_RELATION_TYPES = ("IMPORTS", "DEPENDS_ON")

    def __init__(self, graph: SemanticGraph):
        self.graph = graph
        self.traversal = GraphTraversalEngine(graph)

    def analyze(self, query: GraphQuery) -> GraphAnalysisResult:
        if query.query_type is not QueryType.DEPENDENCY:
            raise ValueError("DependencyAnalyzer requires a DEPENDENCY query.")
        if len(query.source_entities) != 1:
            raise ValueError("Dependency analysis currently requires exactly one source entity.")

        relation_types = parse_relation_types(
            query.constraints.get("relation_types"),
            default=self.DEFAULT_RELATION_TYPES,
        )
        direction = parse_direction(query.constraints.get("direction"))
        max_depth = parse_max_depth(query.constraints.get("max_depth"), default=1)

        traversal = self.traversal.walk(
            query.source_entities[0],
            direction=direction,
            relation_types=relation_types,
            max_depth=max_depth,
        )

        parameters = {
            "relation_types": list(relation_types or ()),
            "direction": direction.value,
            "max_depth": max_depth,
        }
        observations = observations_from_traversal(traversal)
        discovered = traversal.visited_nodes

        return GraphAnalysisResult(
            analysis_id=make_analysis_id(
                analysis_type=AnalysisType.DEPENDENCY,
                query_id=query.query_id,
                graph_fingerprint=traversal.graph_fingerprint,
                parameters=parameters,
            ),
            query_id=query.query_id,
            analysis_type=AnalysisType.DEPENDENCY,
            status=(
                AnalysisStatus.COMPLETED
                if discovered
                else AnalysisStatus.NO_MATCH
            ),
            algorithm=GraphTraversalEngine.ALGORITHM,
            graph_fingerprint=traversal.graph_fingerprint,
            source_entities=query.source_entities,
            discovered_entities=discovered,
            observations=observations,
            evidence=traversal.evidence,
            parameters=parameters,
            metadata={"interpretation": "structural_dependency_observation"},
        )
