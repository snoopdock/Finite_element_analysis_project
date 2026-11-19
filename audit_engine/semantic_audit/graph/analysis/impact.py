"""Bounded reverse-dependency impact analysis over the canonical SemanticGraph.

Impact is a structural candidate report: it identifies observed consumers,
callers, workflow invocations and tests that may be affected by a changed
entity. It does not infer severity, runtime execution, correctness or policy
violations.
"""
from __future__ import annotations

from typing import Any

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph
from audit_engine.semantic_audit.graph.queries.models import GraphQuery, QueryType

from .evidence import EvidenceRecord
from .helpers import make_analysis_id, parse_relation_types
from .identity import graph_fingerprint
from .models import AnalysisStatus, AnalysisType, TraversalDirection
from .observations import SemanticObservation
from .results import GraphAnalysisResult
from .traversal import GraphTraversalEngine


class ImpactAnalyzer:
    """Find direct and transitive reverse dependencies of a changed graph node."""

    DEFAULT_IMPACT_RELATIONS = (
        "IMPORTS", "DEPENDS_ON", "CALLS", "INVOKES", "TESTS",
    )
    OWNERSHIP_RELATIONS = (
        "IMPLEMENTS", "IMPLEMENTED_BY", "DEFINES", "MEMBER_OF",
    )

    def __init__(
        self,
        graph: SemanticGraph,
        *,
        traversal_engine: GraphTraversalEngine | None = None,
    ) -> None:
        self.graph = graph
        self.traversal = (
            traversal_engine if traversal_engine is not None else GraphTraversalEngine(graph)
        )

    def analyze(self, query: GraphQuery) -> GraphAnalysisResult:
        if query.query_type is not QueryType.IMPACT:
            raise ValueError("ImpactAnalyzer requires an IMPACT query.")
        if len(query.source_entities) != 1:
            raise ValueError("Impact analysis currently requires exactly one changed source entity.")

        source = query.source_entities[0]
        constraints = query.constraints
        raw_depth = constraints.get("max_depth", 3)
        if isinstance(raw_depth, bool):
            raise ValueError("max_depth must be an integer between 1 and 5.")
        try:
            max_depth = int(raw_depth)
        except (TypeError, ValueError) as exc:
            raise ValueError("max_depth must be an integer between 1 and 5.") from exc
        if not 1 <= max_depth <= 5:
            raise ValueError("max_depth must be an integer between 1 and 5.")

        max_visited = constraints.get("max_visited_nodes", 500)
        max_steps = constraints.get("max_traversal_steps", 3000)
        if isinstance(max_visited, bool) or not isinstance(max_visited, int) or not 1 <= max_visited <= 2000:
            raise ValueError("max_visited_nodes must be between 1 and 2000.")
        if isinstance(max_steps, bool) or not isinstance(max_steps, int) or not 1 <= max_steps <= 10000:
            raise ValueError("max_traversal_steps must be between 1 and 10000.")

        relations = parse_relation_types(
            constraints.get("relation_types"),
            default=self.DEFAULT_IMPACT_RELATIONS,
        )
        if not relations:
            raise ValueError("Impact analysis requires at least one relation type.")

        # Resolve a file/module/symbol to its immediate ownership peers before
        # walking reverse dependency relationships. This makes a changed file
        # useful without guessing its module or symbol identifiers.
        ownership_visited_limit = max(1, min(50, max_visited // 4))
        ownership_step_limit = max(1, min(500, max_steps // 4))
        ownership = self.traversal.walk(
            source,
            direction=TraversalDirection.BOTH,
            relation_types=self.OWNERSHIP_RELATIONS,
            max_depth=1,
            max_visited_nodes=ownership_visited_limit,
            max_steps=ownership_step_limit,
        )
        owner_depth = {source: 0}
        owner_paths: dict[str, tuple[Any, ...]] = {source: tuple()}
        for hit in ownership.hits:
            owner_depth.setdefault(hit.node_id, hit.depth)
            owner_paths.setdefault(hit.node_id, hit.path)

        seeds = sorted(owner_depth, key=lambda item: (owner_depth[item], item))
        visited_ids = set(seeds)
        evidence_by_id: dict[str, EvidenceRecord] = {
            item.evidence_id: item for item in ownership.evidence
        }
        observations: dict[str, SemanticObservation] = {}
        for step in ownership.steps:
            evidence = evidence_by_id[step.evidence_id]
            observation = SemanticObservation.create(
                subject_id=evidence.subject_id,
                predicate=evidence.predicate,
                object_id=evidence.object_id,
                evidence_ids=(evidence.evidence_id,),
                depth=step.depth,
                metadata={
                    "traversed_from": step.traversed_from,
                    "traversed_to": step.traversed_to,
                    "impact_role": "source_identity_resolution",
                    "changed_source": source,
                },
            )
            observations[observation.observation_id] = observation

        candidate_by_id: dict[str, dict[str, Any]] = {}
        total_examined = ownership.examined_edges
        truncated = ownership.truncated
        stop_reason = ownership.stop_reason
        for seed in seeds:
            if total_examined >= max_steps:
                truncated = True
                stop_reason = "max_traversal_steps"
                break
            if len(visited_ids) >= max_visited:
                truncated = True
                stop_reason = "max_visited_nodes"
                break
            remaining_steps = max_steps - total_examined
            remaining_visited = max(1, max_visited - len(visited_ids) + 1)
            result = self.traversal.walk(
                seed,
                direction=TraversalDirection.INCOMING,
                relation_types=relations,
                max_depth=max_depth,
                max_visited_nodes=remaining_visited,
                max_steps=remaining_steps,
            )
            total_examined += result.examined_edges
            visited_ids.update(result.visited_nodes)
            evidence_by_id.update({item.evidence_id: item for item in result.evidence})
            truncated = truncated or result.truncated
            if result.truncated:
                stop_reason = result.stop_reason

            for step in result.steps:
                evidence = evidence_by_id[step.evidence_id]
                observation = SemanticObservation.create(
                    subject_id=evidence.subject_id,
                    predicate=evidence.predicate,
                    object_id=evidence.object_id,
                    evidence_ids=(evidence.evidence_id,),
                    depth=step.depth,
                    metadata={
                        "traversed_from": step.traversed_from,
                        "traversed_to": step.traversed_to,
                        "impact_role": "reverse_dependency",
                        "changed_source": source,
                        "impact_seed": seed,
                        "ownership_depth": owner_depth[seed],
                    },
                )
                observations.setdefault(observation.observation_id, observation)

            for hit in result.hits:
                if hit.node_id == source or hit.node_id in seeds:
                    continue
                relations_on_path = sorted({step.relation_type for step in hit.path})
                evidence_ids = sorted({step.evidence_id for step in hit.path})
                total_path_length = owner_depth[seed] + hit.depth
                candidate = {
                    "node_id": hit.node_id,
                    "impact_depth": hit.depth,
                    "ownership_depth": owner_depth[seed],
                    "total_path_length": total_path_length,
                    "relation_types": relations_on_path,
                    "evidence_ids": evidence_ids,
                    "path": [step.to_dict() for step in (*owner_paths[seed], *hit.path)],
                    "impact_seed": seed,
                }
                previous = candidate_by_id.get(hit.node_id)
                if previous is None or (
                    candidate["total_path_length"], candidate["node_id"], candidate["impact_seed"]
                ) < (
                    previous["total_path_length"], previous["node_id"], previous["impact_seed"]
                ):
                    candidate_by_id[hit.node_id] = candidate
                elif previous is not None:
                    previous["relation_types"] = sorted(
                        set(previous["relation_types"]) | set(relations_on_path)
                    )
                    previous["evidence_ids"] = sorted(
                        set(previous["evidence_ids"]) | set(evidence_ids)
                    )

            if result.truncated:
                break

        candidates = sorted(
            candidate_by_id.values(),
            key=lambda item: (item["total_path_length"], item["node_id"]),
        )
        discovered = tuple(item["node_id"] for item in candidates)
        direct_count = sum(item["impact_depth"] == 1 for item in candidates)
        transitive_count = len(candidates) - direct_count
        relation_counts: dict[str, int] = {}
        for item in candidates:
            for relation in item["relation_types"]:
                relation_counts[relation] = relation_counts.get(relation, 0) + 1

        parameters = {
            "changed_source": source,
            "direction": "incoming",
            "relation_types": list(relations),
            "ownership_relation_types": list(self.OWNERSHIP_RELATIONS),
            "max_depth": max_depth,
            "max_visited_nodes": max_visited,
            "max_traversal_steps": max_steps,
        }
        return GraphAnalysisResult(
            analysis_id=make_analysis_id(
                analysis_type=AnalysisType.IMPACT,
                query_id=query.query_id,
                graph_fingerprint=graph_fingerprint(self.graph),
                parameters=parameters,
            ),
            query_id=query.query_id,
            analysis_type=AnalysisType.IMPACT,
            status=(
                AnalysisStatus.INCOMPLETE if truncated else
                (AnalysisStatus.COMPLETED if candidates else AnalysisStatus.NO_MATCH)
            ),
            algorithm=GraphTraversalEngine.ALGORITHM,
            graph_fingerprint=graph_fingerprint(self.graph),
            source_entities=(source,),
            discovered_entities=discovered,
            observations=tuple(observations[key] for key in sorted(observations)),
            evidence=tuple(evidence_by_id[key] for key in sorted(evidence_by_id)),
            parameters=parameters,
            metadata={
                "interpretation": "static_reverse_dependency_impact_candidates",
                "impact_direction": "incoming",
                "direct_impact_count": direct_count,
                "transitive_impact_count": transitive_count,
                "impact_candidate_count": len(candidates),
                "impact_candidates": candidates,
                "impact_relation_counts": dict(sorted(relation_counts.items())),
                "ownership_seed_count": len(seeds),
                "ownership_resolution_truncated": ownership.truncated,
                "ownership_evidence_ids": sorted(item.evidence_id for item in ownership.evidence),
                "truncated": truncated,
                "stop_reason": stop_reason,
                "examined_edges": total_examined,
                "visited_node_count": len(visited_ids),
                "runtime_execution_proven": False,
                "severity_assessed": False,
                "semantic_correctness_assessed": False,
            },
        )
