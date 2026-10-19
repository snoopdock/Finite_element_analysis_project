"""Shortest semantic path analysis using deterministic BFS."""

from __future__ import annotations

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph
from audit_engine.semantic_audit.graph.queries.models import GraphQuery, QueryType

from .helpers import (
    make_analysis_id,
    parse_direction,
    parse_max_depth,
    parse_relation_types,
)
from .models import AnalysisStatus, AnalysisType
from .observations import SemanticObservation
from .results import GraphAnalysisResult
from .traversal import GraphTraversalEngine


class PathAnalyzer:
    def __init__(self, graph: SemanticGraph):
        self.graph = graph
        self.traversal = GraphTraversalEngine(graph)

    def analyze(self, query: GraphQuery) -> GraphAnalysisResult:
        if query.query_type is not QueryType.PATH:
            raise ValueError("PathAnalyzer requires a PATH query.")
        if len(query.source_entities) != 1:
            raise ValueError("Path analysis currently requires exactly one source entity.")

        target = str(query.constraints["target_entity"]).strip()
        relation_types = parse_relation_types(query.constraints.get("relation_types"))
        direction = parse_direction(query.constraints.get("direction"))
        max_depth = parse_max_depth(query.constraints.get("max_depth"), default=10)

        max_visited_nodes = query.constraints.get("max_visited_nodes")
        max_steps = query.constraints.get("max_traversal_steps")
        traversal = self.traversal.walk(
            query.source_entities[0],
            direction=direction,
            relation_types=relation_types,
            max_depth=max_depth,
            max_visited_nodes=max_visited_nodes,
            max_steps=max_steps,
        )
        hit = next((item for item in traversal.hits if item.node_id == target), None)

        observations = []
        evidence_ids = set()
        if hit is not None:
            evidence_by_id = {record.evidence_id: record for record in traversal.evidence}
            for depth, step in enumerate(hit.path, start=1):
                record = evidence_by_id[step.evidence_id]
                evidence_ids.add(record.evidence_id)
                observations.append(
                    SemanticObservation.create(
                        subject_id=record.subject_id,
                        predicate=record.predicate,
                        object_id=record.object_id,
                        evidence_ids=(record.evidence_id,),
                        depth=depth,
                        metadata={
                            "traversed_from": step.traversed_from,
                            "traversed_to": step.traversed_to,
                            "path_target": target,
                        },
                    )
                )

        evidence = tuple(
            record
            for record in traversal.evidence
            if record.evidence_id in evidence_ids
        )
        parameters = {
            "target_entity": target,
            "relation_types": list(relation_types or ()),
            "direction": direction.value,
            "max_depth": max_depth,
        }
        if max_visited_nodes is not None:
            parameters["max_visited_nodes"] = max_visited_nodes
        if max_steps is not None:
            parameters["max_traversal_steps"] = max_steps

        return GraphAnalysisResult(
            analysis_id=make_analysis_id(
                analysis_type=AnalysisType.PATH,
                query_id=query.query_id,
                graph_fingerprint=traversal.graph_fingerprint,
                parameters=parameters,
            ),
            query_id=query.query_id,
            analysis_type=AnalysisType.PATH,
            status=(AnalysisStatus.COMPLETED if hit is not None else
                    (AnalysisStatus.INCOMPLETE if traversal.truncated else AnalysisStatus.NO_MATCH)),
            algorithm=GraphTraversalEngine.ALGORITHM,
            graph_fingerprint=traversal.graph_fingerprint,
            source_entities=query.source_entities,
            discovered_entities=((target,) if hit is not None else tuple()),
            observations=tuple(observations),
            evidence=evidence,
            parameters=parameters,
            metadata={
                "interpretation": "path_existence_observation",
                "path_length": len(hit.path) if hit is not None else None,
                "truncated": traversal.truncated,
                "stop_reason": traversal.stop_reason,
                "examined_edges": traversal.examined_edges,
                "visited_node_count": len(traversal.visited_nodes) + 1,
            },
        )
