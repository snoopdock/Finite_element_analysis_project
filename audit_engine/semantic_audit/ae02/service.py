"""AE-02 read-only comparison over AE-01's independently verified publications."""
from __future__ import annotations
from pathlib import Path
from .coverage import from_generation
from .delta import compare_snapshots
from .lifecycle import reconcile_findings
from .snapshots import load_generation
from audit_engine.semantic_audit.ae01.publication import sha, canonical
from audit_engine.semantic_audit.verification.immutable_payload import thaw
from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph, SemanticNode, SemanticEdge
from audit_engine.semantic_audit.evolution import GraphSnapshot
from audit_engine.semantic_audit.evolution.delta import compare_snapshots as compare_graph_snapshots
from .impact import build_impact_plan


def _graph_snapshot(generation):
    """Reuse existing G3 evolution snapshot/delta machinery for policy graph changes."""
    data = thaw(generation.policy_graph)
    graph = SemanticGraph(
        nodes=[SemanticNode(n['id'], n['type'], n['attributes'], n['metadata']) for n in data['nodes']],
        edges=[SemanticEdge(e['source'], e['target'], e['relation'], e['attributes'], e['metadata']) for e in data['edges']])
    return GraphSnapshot.capture(graph)


def compare_generations(before_output: Path | str, after_output: Path | str, *,
                        before_generation: str | None = None,
                        after_generation: str | None = None,
                        max_depth: int = 32, max_tasks: int = 2500) -> dict:
    before = load_generation(before_output, before_generation)
    after = load_generation(after_output, after_generation)
    delta = compare_snapshots(before, after)
    old_coverage, new_coverage = from_generation(before), from_generation(after)
    findings = reconcile_findings(before, after, policy_changed=delta.policy_changed)
    graph_delta = compare_graph_snapshots(_graph_snapshot(before), _graph_snapshot(after))
    impact_plan = build_impact_plan(before, after, graph_delta,
                                    max_depth=max_depth, max_tasks=max_tasks)
    record = {
        'impact_plan': impact_plan,
        'schema': 'ae02/comparison/v1',
        'previous': before.snapshot.to_dict(), 'current': after.snapshot.to_dict(),
        'delta': delta.to_dict(), 'existing_evolution_graph_delta': graph_delta.to_dict(), 'coverage': {
            'previous': old_coverage.to_dict(), 'current': new_coverage.to_dict()},
        'finding_evolution': findings,
        'interpretation': {
            'assurance_complete': after.report['assurance_completeness'] == 'complete_within_declared_scope',
            'impact_plan_complete': not impact_plan['truncated'],
            'impact_plan_scope': impact_plan['completeness'],
            'policy_comparable': not delta.policy_changed,
            'clean_claim_allowed': new_coverage.clean_claim_allowed(),
            'warning': 'Source-derived observations; no claim of software correctness or automatic remediation.',
        },
    }
    record['comparison_sha256'] = sha(canonical(record))
    return record
