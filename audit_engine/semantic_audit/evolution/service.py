"""High-level G3.2 graph evolution service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph
from audit_engine.semantic_audit.findings.models import AuditFinding
from audit_engine.semantic_audit.graph.analysis.context import SemanticContext
from audit_engine.semantic_audit.graph.analysis.results import GraphAnalysisResult
from audit_engine.semantic_audit.verification.receipts import VerificationReceipt

from .delta import GraphDelta, compare_snapshots
from .invalidation import InvalidationReport, assess_transition
from .snapshots import GraphSnapshot
from .topology import TopologyDelta, TopologySummary, compare_topology, summarize_topology


GRAPH_EVOLUTION_RESULT_SCHEMA_VERSION = 'semantic_graph_evolution_result/v1'


@dataclass(frozen=True)
class GraphEvolutionResult:
    before_snapshot: GraphSnapshot
    after_snapshot: GraphSnapshot
    graph_delta: GraphDelta
    before_topology: TopologySummary
    after_topology: TopologySummary
    topology_delta: TopologyDelta
    invalidation_report: InvalidationReport
    schema_version: str = GRAPH_EVOLUTION_RESULT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            'schema_version': self.schema_version,
            'before_snapshot': self.before_snapshot.to_dict(),
            'after_snapshot': self.after_snapshot.to_dict(),
            'graph_delta': self.graph_delta.to_dict(),
            'before_topology': self.before_topology.to_dict(),
            'after_topology': self.after_topology.to_dict(),
            'topology_delta': self.topology_delta.to_dict(),
            'invalidation_report': self.invalidation_report.to_dict(),
        }


class SemanticGraphEvolutionService:
    """Compare canonical graph states without assigning semantic judgment."""

    def compare(
        self,
        *,
        before_graph: SemanticGraph,
        after_graph: SemanticGraph,
        before_context: SemanticContext | None = None,
        after_context: SemanticContext | None = None,
        before_parent_snapshot_id: str | None = None,
        before_metadata: Mapping[str, Any] | None = None,
        after_metadata: Mapping[str, Any] | None = None,
        artifacts: Iterable[GraphAnalysisResult | VerificationReceipt | AuditFinding] = (),
    ) -> GraphEvolutionResult:
        before = GraphSnapshot.capture(
            before_graph,
            semantic_context=before_context,
            parent_snapshot_id=before_parent_snapshot_id,
            metadata=before_metadata,
        )
        after = GraphSnapshot.capture(
            after_graph,
            semantic_context=after_context or before.semantic_context,
            parent_snapshot_id=before.snapshot_id,
            metadata=after_metadata,
        )
        delta = compare_snapshots(before, after)
        before_topology = summarize_topology(before)
        after_topology = summarize_topology(after)
        topology_delta = compare_topology(before_topology, after_topology)
        invalidation = assess_transition(
            before=before,
            after=after,
            delta=delta,
            artifacts=artifacts,
        )
        return GraphEvolutionResult(
            before_snapshot=before,
            after_snapshot=after,
            graph_delta=delta,
            before_topology=before_topology,
            after_topology=after_topology,
            topology_delta=topology_delta,
            invalidation_report=invalidation,
        )
