"""G3.2.1 facade for impact propagation and re-verification planning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from audit_engine.semantic_audit.findings.models import AuditFinding
from audit_engine.semantic_audit.graph.analysis.results import GraphAnalysisResult
from audit_engine.semantic_audit.verification.receipts import VerificationReceipt

from .impact import AuditArtifactDependencyIndex
from .propagation import ImpactPropagationReport, propagate_impacts
from .reverification import ReverificationPlan, ReverificationPolicy, build_reverification_plan
from .service import GraphEvolutionResult


INCREMENTAL_REVERIFICATION_SCHEMA_VERSION = "semantic_incremental_reverification/v1"


@dataclass(frozen=True)
class IncrementalReverificationResult:
    impact_report: ImpactPropagationReport
    reverification_plan: ReverificationPlan
    schema_version: str = INCREMENTAL_REVERIFICATION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "impact_report": self.impact_report.to_dict(),
            "reverification_plan": self.reverification_plan.to_dict(),
        }


class IncrementalReverificationService:
    """Plan only the audit work justified by an already-computed graph transition."""

    def assess(
        self,
        *,
        evolution: GraphEvolutionResult,
        artifacts: Iterable[GraphAnalysisResult | VerificationReceipt | AuditFinding],
        policy: ReverificationPolicy | None = None,
    ) -> IncrementalReverificationResult:
        artifact_tuple = tuple(artifacts)
        index = AuditArtifactDependencyIndex.build(artifact_tuple)
        impact = propagate_impacts(
            before=evolution.before_snapshot,
            after=evolution.after_snapshot,
            delta=evolution.graph_delta,
            dependency_index=index,
        )
        plan = build_reverification_plan(
            report=impact,
            dependency_index=index,
            artifacts=artifact_tuple,
            policy=policy,
        )
        return IncrementalReverificationResult(impact, plan)
