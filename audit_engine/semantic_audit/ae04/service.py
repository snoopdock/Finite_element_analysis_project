"""AE-04: conservative, independently reproducible assurance campaign.

Joins sealed AE-01 architecture findings, AE-02/2.1 source-impact coverage,
and optional AE-03 outcome-replayed mutation evidence. This does not certify
arbitrary Python execution, scientific truth, or repository safety.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from audit_engine.semantic_audit.ae01.publication import canonical, sha
from audit_engine.semantic_audit.ae01.source import module_name
from audit_engine.semantic_audit.ae02 import compare_generations, load_generation
from audit_engine.semantic_audit.ae03.runner import verify_record

SCHEMA = 'ae04/campaign/v1'


def _source_hashes(generation: Any) -> dict[str, str]:
    return {row['path']: row['sha256'] for row in generation.manifest['files']
            if row['status'] == 'included'}


def _mutation_assessment(record: dict | None, generation: Any, root: Path | None,
                         *, replay: bool, required: bool, before_output: Path | str,
                         after_output: Path | str, before_id: str, after_id: str) -> dict:
    if record is None:
        return {'status': 'missing_required' if required else 'not_assessed',
                'score': None, 'sites': 0, 'survived': 0, 'record_sha256': None,
                'scope': 'No claim about test effectiveness.'}
    if root is None or not replay:
        raise ValueError('Mutation integration requires source root and independent outcome replay')
    # The historical sealed audit need not equal all workspace contents, but
    # every declared mutated source MUST refer to the current sealed source bytes.
    audited = _source_hashes(generation)
    for name, digest in record['source_hashes'].items():
        if audited.get(name) != digest:
            raise ValueError(f'AE-03 mutation source is not bound to current AE-01 generation: {name}')
    context = None
    if record.get('impact_provenance') is not None:
        # Recompute the AE-03 scope certificate through the AE-02.1 verified
        # impact adapter; the embedded JSON alone has no authority.
        from audit_engine.semantic_audit.ae03.impact import verified_impact
        context = verified_impact(before_output, after_output,
                    before_generation=before_id, after_generation=after_id)
        if context.to_dict() != record['impact_provenance']:
            raise ValueError('AE-03 impact provenance does not match independently verified AE-02 comparison')
    receipt = verify_record(record, root, replay=True, verified_impact_context=context)
    if receipt['test_outcomes'] != 'replayed':
        raise ValueError('Mutation outcomes were not independently replayed')
    counts = record['counts']
    status = ('inconclusive' if record['assurance'] != 'complete_for_selected_sites' else
              'survivors_require_review' if counts['survived'] else 'selected_mutants_detected')
    return {'status': status, 'score': record['mutation_score'],
            'sites': record['available_sites'], 'survived': counts['survived'],
            'record_sha256': record['record_sha256'],
            'scope': 'Only declared mutation sites and selected tests; no global adequacy claim.'}


def _tasks(impact: dict, report: dict, *, max_output: int) -> tuple[list[dict], bool]:
    """Rank evidence-bound review obligations; never infer defect probability."""
    by_module = {}
    for task in impact['tasks']:
        reasons = set(task['reasons'])
        priority = ('P1' if 'full_scope_recheck_required' in reasons else
                    'P3' if 'transitive_static_import_dependent' in reasons and task['depth'] > 0 else 'P2')
        by_module[task['module']] = {
            'module': task['module'], 'priority': priority,
            'reasons': sorted(reasons), 'source_files': sorted(task['source_files']),
            'occurrence_ids': sorted(task['supporting_occurrences']),
            'finding_ids': [], 'action': task['action']}
    for item in report['findings']:
        witness = item['witness']; finding = item['finding']
        name = module_name(witness['source_id'])
        row = by_module.setdefault(name, {'module': name, 'priority': 'P0',
            'reasons': [], 'source_files': [witness['source_id']],
            'occurrence_ids': [], 'finding_ids': [], 'action': 'review_verified_policy_violation'})
        row['priority'] = 'P0'
        row['reasons'] = sorted(set(row['reasons']) | {'verified_architecture_policy_violation'})
        row['occurrence_ids'] = sorted(set(row['occurrence_ids']) | {witness['occurrence_id']})
        row['finding_ids'] = sorted(set(row['finding_ids']) | {finding['finding_id']})
        row['source_files'] = sorted(set(row['source_files']) | {witness['source_id']})
        row['action'] = 'review_verified_policy_violation'
    ranked = sorted(by_module.values(), key=lambda r: (r['priority'], r['module']))
    return ranked[:max_output], len(ranked) > max_output


def build_campaign(before_output: Path | str, after_output: Path | str, *,
                   before_generation: str | None = None, after_generation: str | None = None,
                   max_depth: int = 32, max_tasks: int = 2500,
                   mutation_record: dict | None = None, mutation_root: Path | None = None,
                   replay_mutation: bool = False, require_mutation: bool = False) -> dict:
    if not 0 <= max_depth <= 10000 or not 1 <= max_tasks <= 100000:
        raise ValueError('Invalid bounded impact budget')
    before = load_generation(before_output, before_generation)
    after = load_generation(after_output, after_generation)
    comparison = compare_generations(before_output, after_output,
                    before_generation=before.snapshot.generation_id,
                    after_generation=after.snapshot.generation_id,
                    max_depth=max_depth, max_tasks=max_tasks)
    if (comparison['previous']['publication_seal_hash'] != before.snapshot.publication_seal_hash or
            comparison['current']['publication_seal_hash'] != after.snapshot.publication_seal_hash):
        raise ValueError('Seal identities disagree with independently verified comparison')
    mutation = _mutation_assessment(mutation_record, after, mutation_root,
                                    replay=replay_mutation, required=require_mutation,
                                    before_output=before_output, after_output=after_output,
                                    before_id=before.snapshot.generation_id, after_id=after.snapshot.generation_id)
    coverage = comparison['coverage']['current']
    plan = comparison['impact_plan']
    tasks, trimmed = _tasks(plan, after.report, max_output=max_tasks)
    complete = (after.report['assurance_completeness'] == 'complete_within_declared_scope' and
                all(row['status'] == 'verified' for row in coverage['entries']) and
                not plan['truncated'] and not trimmed and
                plan['completeness'] != 'full_review_required')
    if after.report['findings']:
        decision = 'verified_policy_violation_requires_review'
    elif not complete or mutation['status'] in ('inconclusive', 'missing_required'):
        decision = 'inconclusive_scope_requires_review'
    elif mutation['status'] == 'survivors_require_review':
        decision = 'test_effectiveness_review_required'
    elif plan['tasks'] or comparison['delta']['policy_changed']:
        decision = 'change_review_required'
    else:
        decision = 'bounded_architecture_policy_pass'
    reasons = []
    if after.report['findings']: reasons.append('verified_policy_findings')
    if not complete: reasons.append('policy_or_impact_coverage_incomplete')
    if mutation['status'] == 'missing_required': reasons.append('required_mutation_evidence_missing')
    if mutation['status'] == 'inconclusive': reasons.append('mutation_evidence_incomplete')
    if mutation['status'] == 'survivors_require_review': reasons.append('selected_mutants_survived')
    if plan['tasks']: reasons.append('source_change_review_obligations')
    if comparison['delta']['policy_changed']: reasons.append('policy_changed')
    record = {'schema': SCHEMA, 'previous': before.snapshot.to_dict(),
              'current': after.snapshot.to_dict(), 'comparison_sha256': comparison['comparison_sha256'],
              'impact_plan_sha256': plan['plan_sha256'],
              'coverage': coverage, 'delta': comparison['delta'],
              'mutation': mutation, 'mutation_record': mutation_record,
              'review': {'tasks': tasks, 'listed': len(tasks), 'truncated': trimmed or plan['truncated'],
                         'full_review_required': plan['completeness'] == 'full_review_required',
                         'evidence_index': plan['evidence_index']},
              'decision': {'status': decision, 'reasons': sorted(set(reasons)),
                           'architecture_clean_claim_within_scope': bool(coverage['clean_claim_allowed']),
                           'test_effectiveness_certified': False,
                           'general_software_correctness_certified': False},
              'configuration': {'max_depth': max_depth, 'max_tasks': max_tasks,
                                'require_mutation': require_mutation},
              'limitations': ['Static import impact is not arbitrary runtime reachability.',
                              'A policy pass does not certify repository correctness.',
                              'Mutation outcomes are limited to selected sites and test oracles.',
                              'Source generations are historical; no live tree equivalence is implied.']}
    record['campaign_sha256'] = sha(canonical(record))
    return record


def verify_campaign(record: dict, before_output: Path | str, after_output: Path | str, *,
                    mutation_root: Path | None = None, replay_mutation: bool = False) -> dict:
    if not isinstance(record, dict) or record.get('schema') != SCHEMA:
        raise ValueError('Invalid AE-04 campaign schema')
    digest = record.get('campaign_sha256')
    if digest != sha(canonical({k:v for k,v in record.items() if k != 'campaign_sha256'})):
        raise ValueError('AE-04 campaign digest mismatch')
    config = record['configuration']
    expected = build_campaign(before_output, after_output,
              before_generation=record['previous']['generation_id'],
              after_generation=record['current']['generation_id'],
              max_depth=config['max_depth'], max_tasks=config['max_tasks'],
              mutation_record=record['mutation_record'], mutation_root=mutation_root,
              replay_mutation=replay_mutation, require_mutation=config['require_mutation'])
    if canonical(record) != canonical(expected):
        raise ValueError('AE-04 campaign disagrees with independently rederived evidence')
    return {'status': 'verified', 'campaign_sha256': digest, 'decision': record['decision']['status'],
            'verification': 'sealed_generations_and_independent_comparison' +
                            ('_and_mutation_outcome_replay' if record['mutation_record'] else '')}
