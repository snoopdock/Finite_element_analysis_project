"""Bounded reverse-dependency impact analysis over the canonical SemanticGraph.

Impact is a structural candidate report: it identifies observed consumers,
callers, workflow invocations and tests that may be affected by a changed
entity. It does not infer severity, runtime execution, correctness or policy
violations.
"""
from __future__ import annotations

import json
from typing import Any

from audit_engine.semantic_audit.graph.analysis.identity import deterministic_id

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph
from audit_engine.semantic_audit.graph.queries.models import GraphQuery, QueryType

from .evidence import EvidenceRecord
from .helpers import make_analysis_id, parse_relation_types
from .identity import edge_fingerprint, graph_fingerprint
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


    MAX_CHANGE_SOURCES = 25
    MAX_CYCLE_NODES = 2000
    MAX_CYCLE_SCAN_EDGES = 50000
    CYCLE_RELATIONS = ("IMPORTS", "DEPENDS_ON")

    def analyze(self, query: GraphQuery) -> GraphAnalysisResult:
        """Analyze one or more changed entities as a deterministic change set.

        Multi-source analysis allocates one global traversal budget across all
        sources, merges duplicate impact candidates with per-source
        attribution, and adds bounded dependency-cycle observations. The
        single-source API remains accepted and uses the same result contract.
        """
        if query.query_type is not QueryType.IMPACT:
            raise ValueError("ImpactAnalyzer requires an IMPACT query.")
        sources = tuple(query.source_entities)
        if not sources:
            raise ValueError("Impact analysis requires at least one changed source entity.")
        if len(sources) > self.MAX_CHANGE_SOURCES:
            raise ValueError(
                f"Impact change sets are limited to {self.MAX_CHANGE_SOURCES} source entities."
            )
        if len(set(sources)) != len(sources):
            raise ValueError("Impact change sets must not contain duplicate source entities.")
        return self._analyze_change_set(query, sources)

    def _analyze_change_set(
        self,
        query: GraphQuery,
        sources: tuple[str, ...],
    ) -> GraphAnalysisResult:
        constraints = dict(query.constraints)
        total_visited = constraints.get("max_visited_nodes", 500)
        total_steps = constraints.get("max_traversal_steps", 3000)
        if (
            isinstance(total_visited, bool) or not isinstance(total_visited, int)
            or not len(sources) <= total_visited <= 2000
        ):
            raise ValueError(
                f"max_visited_nodes must be between source count and 2000 for a change set of {len(sources)}."
            )
        if (
            isinstance(total_steps, bool) or not isinstance(total_steps, int)
            or not len(sources) <= total_steps <= 10000
        ):
            raise ValueError(
                f"max_traversal_steps must be between source count and 10000 for a change set of {len(sources)}."
            )

        ordered_sources = tuple(sorted(sources))
        visited_base, visited_remainder = divmod(total_visited, len(ordered_sources))
        steps_base, steps_remainder = divmod(total_steps, len(ordered_sources))

        source_results: dict[str, GraphAnalysisResult] = {}
        for index, source in enumerate(ordered_sources):
            child_constraints = dict(constraints)
            child_constraints["max_visited_nodes"] = visited_base + (1 if index < visited_remainder else 0)
            child_constraints["max_traversal_steps"] = steps_base + (1 if index < steps_remainder else 0)
            child_query = GraphQuery(
                query_id=query.query_id if len(ordered_sources) == 1 else f"{query.query_id}:{source}",
                query_type=QueryType.IMPACT,
                source_entities=(source,),
                constraints=child_constraints,
            )
            source_results[source] = self._analyze_single(child_query)

        candidate_map: dict[str, dict[str, Any]] = {}
        source_impact_counts: dict[str, int] = {}
        evidence_by_id: dict[str, EvidenceRecord] = {}
        observations_by_id: dict[str, SemanticObservation] = {}
        ownership_evidence_ids: set[str] = set()
        stop_reasons: set[str] = set()
        truncated = False
        examined_edges = 0
        per_source_visited: dict[str, int] = {}

        for source in ordered_sources:
            result = source_results[source]
            metadata = result.metadata
            candidates = metadata.get("impact_candidates", [])
            source_impact_counts[source] = len(candidates)
            truncated = truncated or result.status is AnalysisStatus.INCOMPLETE or bool(metadata.get("truncated"))
            if metadata.get("stop_reason"):
                stop_reasons.add(str(metadata["stop_reason"]))
            examined_edges += int(metadata.get("examined_edges", 0))
            per_source_visited[source] = int(metadata.get("visited_node_count", 0))
            ownership_evidence_ids.update(metadata.get("ownership_evidence_ids", []))

            for evidence in result.evidence:
                evidence_by_id.setdefault(evidence.evidence_id, evidence)
            for observation in result.observations:
                observations_by_id.setdefault(observation.observation_id, observation)

            for raw in candidates:
                if not isinstance(raw, dict) or not isinstance(raw.get("node_id"), str):
                    continue
                candidate = dict(raw)
                node_id = candidate["node_id"]
                path = list(candidate.get("path", []))
                impact_depth = int(candidate.get("impact_depth", 0))
                total_path_length = int(candidate.get("total_path_length", impact_depth))
                existing = candidate_map.get(node_id)
                if existing is None:
                    candidate["affected_by"] = [source]
                    candidate["impact_depth_by_source"] = {source: impact_depth}
                    candidate["total_path_length_by_source"] = {source: total_path_length}
                    candidate["paths_by_source"] = {source: path}
                    candidate_map[node_id] = candidate
                    continue

                existing["affected_by"] = sorted(set(existing.get("affected_by", [])) | {source})
                existing.setdefault("impact_depth_by_source", {})[source] = impact_depth
                existing.setdefault("total_path_length_by_source", {})[source] = total_path_length
                existing.setdefault("paths_by_source", {})[source] = path
                existing["relation_types"] = sorted(
                    set(existing.get("relation_types", [])) | set(candidate.get("relation_types", []))
                )
                existing["evidence_ids"] = sorted(
                    set(existing.get("evidence_ids", [])) | set(candidate.get("evidence_ids", []))
                )
                current_key = (
                    int(existing.get("total_path_length", 10**9)),
                    str(existing.get("impact_seed", "")),
                    json.dumps(existing.get("path", []), sort_keys=True, separators=(",", ":")),
                )
                candidate_key = (
                    total_path_length,
                    str(candidate.get("impact_seed", "")),
                    json.dumps(path, sort_keys=True, separators=(",", ":")),
                )
                if candidate_key < current_key:
                    preserved = {
                        key: existing[key]
                        for key in (
                            "affected_by", "impact_depth_by_source",
                            "total_path_length_by_source", "paths_by_source",
                            "relation_types", "evidence_ids",
                        )
                    }
                    existing.update(candidate)
                    existing.update(preserved)

        candidates = []
        for node_id, candidate in candidate_map.items():
            candidate["affected_by"] = sorted(candidate["affected_by"])
            candidate["affected_by_count"] = len(candidate["affected_by"])
            candidate["shared_change_impact"] = len(candidate["affected_by"]) > 1
            candidate["impact_depth_by_source"] = dict(sorted(candidate["impact_depth_by_source"].items()))
            candidate["total_path_length_by_source"] = dict(sorted(candidate["total_path_length_by_source"].items()))
            candidate["paths_by_source"] = dict(sorted(candidate["paths_by_source"].items()))
            candidate["relation_types"] = sorted(set(candidate.get("relation_types", [])))
            candidate["evidence_ids"] = sorted(set(candidate.get("evidence_ids", [])))
            node = self.graph.get_node(node_id)
            if node is not None:
                path_value = node.attributes.get("path") or node.metadata.get("path")
                candidate["entity_type"] = node.entity_type
                if isinstance(path_value, str) and path_value:
                    candidate["source_path"] = path_value
                candidate["candidate_kind"] = self._candidate_kind(node.entity_type, path_value, node_id)
            candidates.append(candidate)
        candidates.sort(key=lambda item: (item.get("total_path_length", 0), item["node_id"]))

        impacted_node_ids = set(ordered_sources)
        for candidate in candidates:
            impacted_node_ids.add(candidate["node_id"])
            seed = candidate.get("impact_seed")
            if isinstance(seed, str):
                impacted_node_ids.add(seed)
            for path_step in candidate.get("path", []):
                if isinstance(path_step, dict):
                    for key in ("source_id", "target_id", "traversed_from", "traversed_to"):
                        value = path_step.get(key)
                        if isinstance(value, str):
                            impacted_node_ids.add(value)
        impacted_node_ids = {node_id for node_id in impacted_node_ids if self.graph.has_node(node_id)}

        cycles, cycle_status, cycle_evidence, cycle_observations, cycle_scan_count = (
            self._dependency_cycles(impacted_node_ids)
        )
        for evidence in cycle_evidence:
            evidence_by_id.setdefault(evidence.evidence_id, evidence)
        for observation in cycle_observations:
            observations_by_id.setdefault(observation.observation_id, observation)

        shared_candidates = [item for item in candidates if item["shared_change_impact"]]
        direct_count = sum(
            min(item.get("impact_depth_by_source", {}).values(), default=item.get("impact_depth", 0)) == 1
            for item in candidates
        )
        transitive_count = len(candidates) - direct_count
        relation_counts: dict[str, int] = {}
        for item in candidates:
            for relation in item.get("relation_types", []):
                relation_counts[relation] = relation_counts.get(relation, 0) + 1

        risk_indicators: list[dict[str, Any]] = []
        for cycle in cycles:
            risk_indicators.append({
                "code": "dependency_cycle_observed",
                "basis": "strongly_connected_component",
                "cycle_id": cycle["cycle_id"],
                "node_ids": list(cycle["node_ids"]),
                "evidence_ids": list(cycle["evidence_ids"]),
                "severity_assessed": False,
            })
        if shared_candidates:
            risk_indicators.append({
                "code": "shared_impact_overlap",
                "basis": "same_candidate_reachable_from_multiple_changed_sources",
                "candidate_count": len(shared_candidates),
                "node_ids": [item["node_id"] for item in shared_candidates[:100]],
                "evidence_ids": sorted({
                    evidence_id
                    for item in shared_candidates
                    for evidence_id in item.get("evidence_ids", [])
                }),
                "severity_assessed": False,
            })
        if truncated:
            risk_indicators.append({
                "code": "impact_frontier_incomplete",
                "basis": "one_or_more_source_traversals_reached_a_declared_budget",
                "stop_reasons": sorted(stop_reasons),
                "severity_assessed": False,
            })
        if cycle_status != "complete":
            risk_indicators.append({
                "code": "dependency_cycle_scan_incomplete",
                "basis": cycle_status,
                "severity_assessed": False,
            })

        source_node_kinds = {
            source: self._candidate_kind(
                self.graph.get_node(source).entity_type,
                (self.graph.get_node(source).attributes.get("path") or self.graph.get_node(source).metadata.get("path")),
                source,
            )
            for source in ordered_sources
        }
        effective_relations = parse_relation_types(
            constraints.get("relation_types"),
            default=self.DEFAULT_IMPACT_RELATIONS,
        ) or ()
        parameters = {
            "changed_sources": list(ordered_sources),
            "direction": "incoming",
            "relation_types": list(effective_relations),
            "ownership_relation_types": list(self.OWNERSHIP_RELATIONS),
            "max_depth": constraints.get("max_depth", 3),
            "max_visited_nodes": total_visited,
            "max_traversal_steps": total_steps,
            "cycle_relation_types": list(self.CYCLE_RELATIONS),
            "max_cycle_nodes": self.MAX_CYCLE_NODES,
            "max_cycle_scan_edges": self.MAX_CYCLE_SCAN_EDGES,
        }
        fingerprint = graph_fingerprint(self.graph)
        return GraphAnalysisResult(
            analysis_id=make_analysis_id(
                analysis_type=AnalysisType.IMPACT,
                query_id=query.query_id,
                graph_fingerprint=fingerprint,
                parameters=parameters,
            ),
            query_id=query.query_id,
            analysis_type=AnalysisType.IMPACT,
            status=(
                AnalysisStatus.INCOMPLETE if truncated or cycle_status != "complete" else
                (AnalysisStatus.COMPLETED if candidates else AnalysisStatus.NO_MATCH)
            ),
            algorithm=GraphTraversalEngine.ALGORITHM,
            graph_fingerprint=fingerprint,
            source_entities=ordered_sources,
            discovered_entities=tuple(item["node_id"] for item in candidates),
            observations=tuple(observations_by_id[key] for key in sorted(observations_by_id)),
            evidence=tuple(evidence_by_id[key] for key in sorted(evidence_by_id)),
            parameters=parameters,
            metadata={
                "interpretation": "static_change_set_impact_candidates",
                "impact_direction": "incoming",
                "changed_source_count": len(ordered_sources),
                "changed_sources": list(ordered_sources),
                "source_node_kinds": source_node_kinds,
                "source_impact_counts": dict(sorted(source_impact_counts.items())),
                "direct_impact_count": direct_count,
                "transitive_impact_count": transitive_count,
                "impact_candidate_count": len(candidates),
                "unique_impact_count": len(candidates),
                "shared_impact_count": len(shared_candidates),
                "impact_candidates": candidates,
                "impact_relation_counts": dict(sorted(relation_counts.items())),
                "ownership_seed_count": sum(
                    int(source_results[source].metadata.get("ownership_seed_count", 0))
                    for source in ordered_sources
                ),
                "ownership_resolution_truncated": any(
                    bool(source_results[source].metadata.get("ownership_resolution_truncated"))
                    for source in ordered_sources
                ),
                "ownership_evidence_ids": sorted(ownership_evidence_ids),
                "truncated": truncated,
                "stop_reason": sorted(stop_reasons)[0] if stop_reasons else None,
                "stop_reasons": sorted(stop_reasons),
                "examined_edges": examined_edges,
                "visited_node_count": len(impacted_node_ids),
                "per_source_visited_node_counts": dict(sorted(per_source_visited.items())),
                "dependency_cycles": cycles,
                "dependency_cycle_count": len(cycles),
                "cycle_analysis_status": cycle_status,
                "cycle_scan_edge_count": cycle_scan_count,
                "risk_indicators": risk_indicators,
                "affected_test_candidate_ids": [
                    item["node_id"] for item in candidates if item.get("candidate_kind") == "test"
                ],
                "affected_workflow_candidate_ids": [
                    item["node_id"] for item in candidates if item.get("candidate_kind") == "workflow"
                ],
                "affected_symbol_candidate_ids": [
                    item["node_id"] for item in candidates if item.get("candidate_kind") == "symbol"
                ],
                "runtime_execution_proven": False,
                "severity_assessed": False,
                "semantic_correctness_assessed": False,
                "automatic_approval_permitted": False,
                "authoritative_graph_mutation_permitted": False,
            },
        )

    @staticmethod
    def _candidate_kind(entity_type: str, path: Any, node_id: str) -> str:
        normalized_type = str(entity_type or "").casefold()
        normalized_path = str(path or "")
        if "test" in normalized_type or normalized_path.startswith("tests/"):
            return "test"
        if normalized_path.startswith(".github/workflows/") or "workflow" in normalized_type:
            return "workflow"
        if "symbol" in normalized_type or "function" in normalized_type or "class" in normalized_type or node_id.startswith("symbol:"):
            return "symbol"
        if "module" in normalized_type:
            return "module"
        if normalized_path:
            return "file"
        return "other"

    def _dependency_cycles(
        self,
        impacted_node_ids: set[str],
    ) -> tuple[list[dict[str, Any]], str, tuple[EvidenceRecord, ...], tuple[SemanticObservation, ...], int]:
        """Find bounded dependency SCCs in the induced impacted subgraph.

        This is structural cycle detection over IMPORTS/DEPENDS_ON only. It
        does not infer that a cycle is harmful or that any code path executes.
        """
        nodes = sorted(impacted_node_ids)
        if len(nodes) > self.MAX_CYCLE_NODES:
            return [], "incomplete_node_limit", tuple(), tuple(), 0
        if not nodes:
            return [], "complete", tuple(), tuple(), 0

        if len(self.graph.edges) > self.MAX_CYCLE_SCAN_EDGES:
            return [], "incomplete_edge_limit", tuple(), tuple(), 0
        scanned_edges = sorted(
            self.graph.edges,
            key=lambda edge: (
                edge.source_id, edge.target_id, edge.relation_type,
                edge_fingerprint(edge),
            ),
        )
        node_set = set(nodes)
        relation_set = set(self.CYCLE_RELATIONS)
        relevant = [
            edge for edge in scanned_edges
            if edge.source_id in node_set and edge.target_id in node_set
            and edge.relation_type in relation_set
        ]

        adjacency: dict[str, set[str]] = {node: set() for node in nodes}
        reverse: dict[str, set[str]] = {node: set() for node in nodes}
        for edge in relevant:
            adjacency[edge.source_id].add(edge.target_id)
            reverse[edge.target_id].add(edge.source_id)

        # Iterative Kosaraju avoids recursion limits on generated repositories.
        visited: set[str] = set()
        finish_order: list[str] = []
        for start in nodes:
            if start in visited:
                continue
            visited.add(start)
            stack: list[tuple[str, int, list[str]]] = [
                (start, 0, sorted(adjacency[start]))
            ]
            while stack:
                current, index, neighbors = stack[-1]
                if index < len(neighbors):
                    neighbor = neighbors[index]
                    stack[-1] = (current, index + 1, neighbors)
                    if neighbor not in visited:
                        visited.add(neighbor)
                        stack.append((neighbor, 0, sorted(adjacency[neighbor])))
                else:
                    finish_order.append(current)
                    stack.pop()

        assigned: set[str] = set()
        components: list[list[str]] = []
        for start in reversed(finish_order):
            if start in assigned:
                continue
            component: list[str] = []
            stack = [start]
            assigned.add(start)
            while stack:
                current = stack.pop()
                component.append(current)
                for neighbor in sorted(reverse[current], reverse=True):
                    if neighbor not in assigned:
                        assigned.add(neighbor)
                        stack.append(neighbor)
            components.append(sorted(component))

        cycles: list[dict[str, Any]] = []
        evidence_by_id: dict[str, EvidenceRecord] = {}
        observations_by_id: dict[str, SemanticObservation] = {}
        for component in sorted(components, key=lambda value: tuple(value)):
            component_set = set(component)
            internal_edges = [
                edge for edge in relevant
                if edge.source_id in component_set and edge.target_id in component_set
            ]
            self_loop = any(edge.source_id == edge.target_id for edge in internal_edges)
            if len(component) == 1 and not self_loop:
                continue
            cycle_edges = sorted(
                internal_edges,
                key=lambda edge: (edge.source_id, edge.target_id, edge.relation_type, edge_fingerprint(edge)),
            )
            cycle_evidence_ids: list[str] = []
            for edge in cycle_edges:
                evidence = EvidenceRecord.from_edge(edge)
                evidence_by_id.setdefault(evidence.evidence_id, evidence)
                cycle_evidence_ids.append(evidence.evidence_id)
                observation = SemanticObservation.create(
                    subject_id=edge.source_id,
                    predicate=edge.relation_type,
                    object_id=edge.target_id,
                    evidence_ids=(evidence.evidence_id,),
                    depth=1,
                    metadata={"impact_role": "dependency_cycle", "cycle_node_ids": component},
                )
                observations_by_id.setdefault(observation.observation_id, observation)
            relations = sorted({edge.relation_type for edge in cycle_edges})
            cycle_id = deterministic_id(
                "dependency-cycle",
                {
                    "node_ids": component,
                    "relations": relations,
                    "edge_evidence_ids": sorted(cycle_evidence_ids),
                },
                length=24,
            )
            cycles.append({
                "cycle_id": cycle_id,
                "node_ids": component,
                "relation_types": relations,
                "edge_count": len(cycle_edges),
                "evidence_ids": sorted(set(cycle_evidence_ids)),
                "self_loop": self_loop,
                "interpretation": "observed_structural_dependency_cycle",
            })

        status = "complete"
        return (
            sorted(cycles, key=lambda item: item["cycle_id"]),
            status,
            tuple(evidence_by_id[key] for key in sorted(evidence_by_id)),
            tuple(observations_by_id[key] for key in sorted(observations_by_id)),
            len(scanned_edges),
        )

    def _analyze_single(self, query: GraphQuery) -> GraphAnalysisResult:
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
                "automatic_approval_permitted": False,
                "authoritative_graph_mutation_permitted": False,
            },
        )
