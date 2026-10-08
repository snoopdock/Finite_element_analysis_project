#!/usr/bin/env python3
"""Deterministic G3.2.1 acceptance artifact generator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.evolution import (
    ArtifactValidity,
    AuditLongTermMemory,
    AuditMemoryQueryService,
    IncrementalReverificationService,
    MemoryQuery,
    SemanticGraphEvolutionService,
)
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.analysis.context import SemanticContext
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.verification import (
    ObservationContractVerifier,
    VerificationObligation,
    VerificationService,
    VerifierRegistry,
)


def build_graph(*, local_change=False, remote_change=False, remove_dependency=False):
    graph = SemanticGraph()
    graph.add_node(SemanticNode('a', 'Module'))
    graph.add_node(SemanticNode('b', 'Module'))
    graph.add_node(SemanticNode('c', 'Module'))
    if not remove_dependency:
        graph.add_edge(SemanticEdge('a', 'b', 'DEPENDS_ON', metadata={'source_id': 'code:1'}))
    if local_change:
        graph.add_edge(SemanticEdge('a', 'c', 'DEPENDS_ON', metadata={'source_id': 'code:2'}))
    if remote_change:
        graph.add_node(SemanticNode('remote', 'Module'))
    return graph


def analysis_and_receipt(graph, context):
    analysis = SemanticGraphAnalysisService(graph, semantic_context=context).analyze(
        GraphQuery('g321-validation', QueryType.DEPENDENCY, ['a'], {'max_depth': 1})
    )
    observation = analysis.observations[0]
    obligation = VerificationObligation.from_analysis_result(
        analysis,
        obligation_type='observation_contract',
        observation_ids=[observation.observation_id],
        evidence_ids=list(observation.evidence_ids),
        requested_verifier_ids=['observation-contract'],
        parameters={
            'subject_id': observation.subject_id,
            'predicate': observation.predicate,
            'object_id': observation.object_id,
        },
    )
    registry = VerifierRegistry()
    registry.register(ObservationContractVerifier())
    receipt = VerificationService(registry).verify(
        obligation, analysis, verifier_id='observation-contract'
    )
    return analysis, receipt


def run_validation(output_path: Path):
    context = SemanticContext(relationship_vocabulary_version='repo-relations/v1')
    before_graph = build_graph()
    analysis, receipt = analysis_and_receipt(before_graph, context)

    remote_evolution = SemanticGraphEvolutionService().compare(
        before_graph=before_graph,
        after_graph=build_graph(remote_change=True),
        before_context=context,
    )
    remote = IncrementalReverificationService().assess(
        evolution=remote_evolution,
        artifacts=[analysis, receipt],
    )

    local_evolution = SemanticGraphEvolutionService().compare(
        before_graph=before_graph,
        after_graph=build_graph(local_change=True),
        before_context=context,
    )
    local = IncrementalReverificationService().assess(
        evolution=local_evolution,
        artifacts=[analysis, receipt],
    )

    stale_evolution = SemanticGraphEvolutionService().compare(
        before_graph=before_graph,
        after_graph=build_graph(remove_dependency=True),
        before_context=context,
    )
    stale = IncrementalReverificationService().assess(
        evolution=stale_evolution,
        artifacts=[analysis, receipt],
    )

    memory = AuditLongTermMemory()
    memory.append_artifact(
        artifact_type='analysis',
        artifact_id=analysis.analysis_id,
        snapshot_id=remote_evolution.before_snapshot.snapshot_id,
        payload=analysis.to_dict(),
    )
    memory.append_artifact(
        artifact_type='verification_receipt',
        artifact_id=receipt.receipt_id,
        snapshot_id=remote_evolution.before_snapshot.snapshot_id,
        payload=receipt.to_dict(),
    )
    memory_matches = AuditMemoryQueryService(memory).execute(
        MemoryQuery(evidence_ids=receipt.evidence_ids)
    )

    local_analysis_impact = local.impact_report.by_id(analysis.analysis_id)
    stale_receipt_impact = stale.impact_report.by_id(receipt.receipt_id)
    receipt_task = next(
        task for task in stale.reverification_plan.tasks
        if task.artifact_id == receipt.receipt_id
    )

    checks = {
        'unrelated_change_keeps_local_analysis_current': remote.impact_report.by_id(analysis.analysis_id).validity is ArtifactValidity.CURRENT,
        'unrelated_change_creates_no_reverification_tasks': remote.reverification_plan.is_empty,
        'relevant_neighborhood_change_requires_recheck': local_analysis_impact.validity is ArtifactValidity.RECHECK_REQUIRED,
        'direct_evidence_loss_marks_receipt_stale': stale_receipt_impact.validity is ArtifactValidity.STALE,
        'stale_receipt_preserves_analysis_prerequisite': receipt_task.prerequisite_artifact_ids == (analysis.analysis_id,),
        'reverification_plan_is_policy_versioned': bool(stale.reverification_plan.policy_version),
        'memory_query_returns_evidence_lineage': len(memory_matches.records) == 2,
        'memory_query_is_read_only': len(memory) == 2,
        'impact_contract_present': Path('specs/contracts/semantic_impact_propagation_contract.yaml').is_file(),
        'reverification_contract_present': Path('specs/contracts/semantic_reverification_plan_contract.yaml').is_file(),
        'memory_query_contract_present': Path('specs/contracts/audit_memory_query_contract.yaml').is_file(),
        'incremental_boundary_contract_present': Path('specs/contracts/incremental_reverification_contract.yaml').is_file(),
    }

    payload = {
        'schema_version': 'semantic_incremental_reverification_validation/v1',
        'checks': checks,
        'passed': all(checks.values()),
        'remote_change': remote.to_dict(),
        'local_change': local.to_dict(),
        'evidence_loss': stale.to_dict(),
        'memory_query': memory_matches.to_dict(),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')
    for name, passed in checks.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    if not payload['passed']:
        return payload, 1
    print('G3.2.1 incremental impact and re-verification validation passed.')
    return payload, 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='artifacts/semantic_incremental_reverification_validation.json')
    args = parser.parse_args()
    _, status = run_validation(Path(args.output))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
