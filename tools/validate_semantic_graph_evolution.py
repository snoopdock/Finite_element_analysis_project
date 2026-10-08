#!/usr/bin/env python3
"""Deterministic G3.2.0 graph evolution acceptance artifact generator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.evolution import AuditLongTermMemory, SemanticGraphEvolutionService
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.analysis.context import SemanticContext
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.verification import ObservationContractVerifier, VerifierRegistry, VerificationObligation, VerificationService


def build_graph(include_call=False):
    graph = SemanticGraph()
    graph.add_node(SemanticNode('a', 'Module'))
    graph.add_node(SemanticNode('b', 'Module'))
    graph.add_node(SemanticNode('c', 'Module'))
    graph.add_edge(SemanticEdge('a', 'b', 'DEPENDS_ON', metadata={'source_id': 'code:1'}))
    if include_call:
        graph.add_edge(SemanticEdge('b', 'c', 'CALLS', metadata={'source_id': 'code:2'}))
    return graph


def run_validation(output_path: Path):
    context = SemanticContext(relationship_vocabulary_version='repo-relations/v1')
    before_graph = build_graph()
    analysis = SemanticGraphAnalysisService(before_graph, semantic_context=context).analyze(
        GraphQuery('g320-validation', QueryType.DEPENDENCY, ['a'], {'max_depth': 1})
    )
    observation = analysis.observations[0]
    obligation = VerificationObligation.from_analysis_result(
        analysis,
        obligation_type='observation_contract',
        observation_ids=[observation.observation_id],
        evidence_ids=list(observation.evidence_ids),
        requested_verifier_ids=['observation-contract'],
        parameters={'subject_id': 'a', 'predicate': 'DEPENDS_ON', 'object_id': 'b'},
    )
    registry = VerifierRegistry()
    registry.register(ObservationContractVerifier())
    receipt = VerificationService(registry).verify(obligation, analysis, verifier_id='observation-contract')

    evolution = SemanticGraphEvolutionService().compare(
        before_graph=before_graph,
        after_graph=build_graph(include_call=True),
        before_context=context,
        artifacts=[analysis, receipt],
        before_metadata={'revision': 'before'},
        after_metadata={'revision': 'after'},
    )

    memory = AuditLongTermMemory()
    memory.append_artifact(
        artifact_type='graph_snapshot',
        artifact_id=evolution.before_snapshot.snapshot_id,
        snapshot_id=evolution.before_snapshot.snapshot_id,
        payload=evolution.before_snapshot.to_dict(),
    )
    memory.append_artifact(
        artifact_type='graph_delta',
        artifact_id=evolution.graph_delta.delta_id,
        snapshot_id=evolution.after_snapshot.snapshot_id,
        payload=evolution.graph_delta.to_dict(),
    )

    invalidations = evolution.invalidation_report.artifacts
    checks = {
        'snapshot_identity_bound_to_semantic_context': bool(evolution.before_snapshot.semantic_context_fingerprint),
        'after_snapshot_has_lineage': evolution.after_snapshot.parent_snapshot_id == evolution.before_snapshot.snapshot_id,
        'graph_delta_detects_added_relation': len(evolution.graph_delta.added_edges) == 1,
        'topology_delta_is_descriptive': evolution.topology_delta.to_dict()['interpretation_boundary'] == 'descriptive_topology_only',
        'unrelated_graph_change_requires_recheck': bool(invalidations) and all(item.validity.value == 'recheck_required' for item in invalidations),
        'memory_is_append_only_artifact_ledger': len(memory) == 2,
        'snapshot_contract_present': Path('specs/contracts/semantic_graph_snapshot_contract.yaml').is_file(),
        'evolution_contract_present': Path('specs/contracts/semantic_graph_evolution_contract.yaml').is_file(),
        'invalidation_contract_present': Path('specs/contracts/semantic_audit_invalidation_contract.yaml').is_file(),
        'memory_contract_present': Path('specs/contracts/audit_long_term_memory_contract.yaml').is_file(),
    }
    payload = {
        'schema_version': 'semantic_graph_evolution_validation/v1',
        'checks': checks,
        'passed': all(checks.values()),
        'evolution': evolution.to_dict(),
        'memory': memory.to_dict(),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')
    for name, passed in checks.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    if not payload['passed']:
        return payload, 1
    print('G3.2.0 semantic graph evolution validation passed.')
    return payload, 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='artifacts/semantic_graph_evolution_validation.json')
    args = parser.parse_args()
    _, status = run_validation(Path(args.output))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
