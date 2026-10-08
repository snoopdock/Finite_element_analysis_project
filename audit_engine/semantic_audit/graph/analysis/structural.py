"""One-hop structural neighborhood analysis."""

from __future__ import annotations

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph
from audit_engine.semantic_audit.graph.queries.models import GraphQuery, QueryType

from .helpers import (
    make_analysis_id,
    observations_from_traversal,
    parse_direction,
    parse_relation_types,
)
from .models import AnalysisStatus, AnalysisType
from .results import GraphAnalysisResult
from .traversal import GraphTraversalEngine


class StructuralAnalyzer:
    def __init__(self, graph: SemanticGraph):
        self.graph = graph
        self.traversal = GraphTraversalEngine(graph)

    def analyze(self, query: GraphQuery) -> GraphAnalysisResult:
        if query.query_type is not QueryType.STRUCTURAL:
            raise ValueError("StructuralAnalyzer requires a STRUCTURAL query.")
        if len(query.source_entities) != 1:
            raise ValueError("Structural analysis currently requires exactly one source entity.")

        direction = parse_direction(query.constraints.get("direction"))
        relation_types = parse_relation_types(query.constraints.get("relation_types"))
        traversal = self.traversal.walk(
            query.source_entities[0],
            direction=direction,
            relation_types=relation_types,
            max_depth=1,
        )
        parameters = {
            "relation_types": list(relation_types or ()),
            "direction": direction.value,
            "max_depth": 1,
        }

        return GraphAnalysisResult(
            analysis_id=make_analysis_id(
                analysis_type=AnalysisType.STRUCTURAL,
                query_id=query.query_id,
                graph_fingerprint=traversal.graph_fingerprint,
                parameters=parameters,
            ),
            query_id=query.query_id,
            analysis_type=AnalysisType.STRUCTURAL,
            status=(
                AnalysisStatus.COMPLETED
                if traversal.hits
                else AnalysisStatus.NO_MATCH
            ),
            algorithm=GraphTraversalEngine.ALGORITHM,
            graph_fingerprint=traversal.graph_fingerprint,
            source_entities=query.source_entities,
            discovered_entities=traversal.visited_nodes,
            observations=observations_from_traversal(traversal),
            evidence=traversal.evidence,
            parameters=parameters,
            metadata={"interpretation": "one_hop_structure_observation"},
        )
