"""AE-07: evidence-conservative portfolio over independently verified AE-06 assessments.

No risk scoring, release authorization, or authenticated reviewer identities are inferred.
All evidence is rederived using the native AE-06/AE-01 verification paths.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from audit_engine.semantic_audit.ae01.publication import canonical, sha, _no_symlink_components
from audit_engine.semantic_audit.ae02.snapshots import load_generation
from audit_engine.semantic_audit.ae06.publication import _stored, verify_assessment_publication
from audit_engine.semantic_audit.verification.immutable_payload import thaw

SCHEMA = 'ae07/assurance_portfolio/v1'
REQUIRED = ('origin_before', 'flagged_output', 'current_output', 'origin_campaign',
            'origin_review', 'followup_campaign')
OPTIONAL = ('history_outputs', 'history_campaigns', 'origin_mutation_root',
            'followup_mutation_root', 'replay_origin_mutation', 'replay_followup_mutation')


def _validated_entries(entries: list[dict]) -> list[dict]:
    if not isinstance(entries, list) or not 1 <= len(entries) <= 16:
        raise ValueError('Portfolio requires between 1 and 16 explicit AE-06 assessments')
    normalized = []
    seen = set()
    for item in entries:
        if not isinstance(item, dict) or set(item) != {'assessment_output', 'inputs'}:
            raise ValueError('Portfolio entries require exactly assessment_output and inputs')
        inp = item['inputs']
        if not isinstance(inp, dict) or set(REQUIRED) - set(inp) or set(inp) - (set(REQUIRED) | set(OPTIONAL)):
            raise ValueError('AE-06 input schema does not match the portfolio contract')
        if any(not isinstance(inp[name], str) or not inp[name].strip() for name in REQUIRED):
            raise ValueError('Required evidence paths must be nonempty strings')
        if not isinstance(item['assessment_output'], str) or not item['assessment_output'].strip():
            raise ValueError('Invalid assessment publication path')
        clean = {name: inp[name] for name in REQUIRED}
        for field in ('history_outputs', 'history_campaigns'):
            value = inp.get(field, [])
            if not isinstance(value, list) or len(value) > 32 or any(not isinstance(x, str) or not x for x in value):
                raise ValueError(f'Invalid {field} history sequence')
            clean[field] = value[:]
        for field in ('origin_mutation_root', 'followup_mutation_root'):
            v = inp.get(field)
            if v is not None and (not isinstance(v, str) or not v):
                raise ValueError(f'Invalid {field}')
            clean[field] = v
        for field in ('replay_origin_mutation', 'replay_followup_mutation'):
            v = inp.get(field, False)
            if not isinstance(v, bool):
                raise ValueError(f'Invalid {field} flag')
            clean[field] = v
        p = Path(item['assessment_output']).absolute()
        _no_symlink_components(p)
        if str(p) in seen:
            raise ValueError('Duplicate assessment publication is not an independent input')
        seen.add(str(p))
        for value in (clean[name] for name in REQUIRED):
            _no_symlink_components(Path(value).absolute())
        for value in (*clean['history_outputs'], *clean['history_campaigns']):
            _no_symlink_components(Path(value).absolute())
        normalized.append({'assessment_output': str(p), 'inputs': clean})
    # Permuting the input manifest cannot change the portfolio result.
    return sorted(normalized, key=lambda x: x['assessment_output'])


def _native_inputs(data: dict) -> dict:
    return {k: tuple(v) if k in ('history_outputs', 'history_campaigns') else v
            for k, v in data.items()}


def _load_verified(entry: dict) -> tuple[dict, Any, dict]:
    path = Path(entry['assessment_output'])
    kwargs = _native_inputs(entry['inputs'])
    receipt = verify_assessment_publication(path, **kwargs)
    record = _stored(path)  # re-read after native verification; check for TOCTOU
    if receipt['assessment_sha256'] != record['assessment_sha256']:
        raise ValueError('AE-06 publication changed between validation and evidence loading')
    generation = load_generation(kwargs['current_output'])
    if generation.snapshot.to_dict() != record['inputs']['current']:
        raise ValueError('AE-01 current generation differs from AE-06 verified source binding')
    return record, generation, receipt


def _priority_for(case_status: str) -> str:
    if case_status in ('persistent_violation','reintroduced_violation','changed_violation_open'):
        return 'P0'
    if case_status in ('not_assessable','review_required'):
        return 'P1'
    if case_status == 'bounded_absence_candidate':
        return 'P2'
    raise ValueError(f'Unexpected AE-06 case status: {case_status}')


def build_portfolio(entries: list[dict]) -> dict:
    """Join *verified* publications. Never infer independent policy coverage or approval."""
    normalized = _validated_entries(entries)
    input_rows: list[dict] = []
    tasks: dict[str, dict] = {}
    generations = set()
    policies = set()
    source_scopes = set()
    incomplete = False
    open_finding_count = 0
    required_review = 0
    all_current_findings: dict[str, dict] = {}
    for item in normalized:
        assessment, current, receipt = _load_verified(item)
        gen = current.snapshot
        gen_id = gen.generation_id
        generations.add(gen_id)
        policies.add(sha(canonical(thaw(current.policy))))
        scope = sorted(row['path'] for row in current.manifest['files'] if row['status'] == 'included')
        source_scopes.add(sha(canonical(scope)))
        status = assessment['assurance']['status']
        complete = current.report['assurance_completeness'] == 'complete_within_declared_scope'
        incomplete |= not complete or status == 'inconclusive_requires_review'
        current_findings = thaw(current.report['findings'])
        open_finding_count += len(current_findings)
        assessment_id = assessment['assessment_sha256']
        input_rows.append({'assessment_sha256': assessment_id,
                           'publication_generation': receipt['generation'],
                           'current_generation_id': gen_id,
                           'current_source_manifest_sha256': gen.source_manifest_hash,
                           'current_policy_sha256': gen.policy_hash,
                           'current_scope_sha256': sha(canonical(scope)),
                           'current_assurance_completeness': current.report['assurance_completeness'],
                           'assessment_status': status,
                           'assessment_case_count': len(assessment['cases']),
                           'current_verified_findings': len(current_findings)})
        for case in assessment['cases']:
            prio = _priority_for(case['status'])
            if prio in ('P1','P2'): required_review += 1
            key = sha(canonical({'assessment': assessment_id, 'case': case['case_id']}))
            tasks[key] = {'id': key, 'kind': 'remediation_review', 'priority': prio,
                          'assessment_sha256': assessment_id,
                          'source_file': case['source_file'], 'source_sha256': case['current_source_sha256'],
                          'rule_id': case['rule_id'], 'origin_finding_id': case['origin_finding_id'],
                          'status': case['status'], 'reasons': sorted(set(case['reasons'])),
                          'action': ('review_verified_violation' if prio == 'P0' else
                                     'investigate_incomplete_evidence' if prio == 'P1' else
                                     'human_closure_decision_required')}
        for f in current_findings:
            fid = f['finding']['finding_id']
            wit = f['witness']
            key = sha(canonical({'current_generation': gen_id, 'finding': fid}))
            value = {'id': key, 'kind': 'verified_finding', 'priority': 'P0',
                     'current_generation_id': gen_id, 'finding_id': fid,
                     'rule_id': f['finding']['rule_id'], 'source_file': wit['source_id'],
                     'source_sha256': wit['source_sha256'], 'line': wit['line'],
                     'column': wit.get('column', 0), 'occurrence_id': wit['occurrence_id'],
                     'status': 'verified_policy_violation', 'action': 'review_verified_violation'}
            if key in all_current_findings and all_current_findings[key] != value:
                raise ValueError('Conflicting witnesses for the same sealed finding')
            all_current_findings[key] = value
    tasks.update(all_current_findings)
    incomparable = len(generations) != 1 or len(policies) != 1 or len(source_scopes) != 1
    if open_finding_count:
        gate = 'blocked_verified_policy_violations'
    elif incomparable:
        gate = 'inconclusive_incomparable_source_or_policy'
    elif incomplete:
        gate = 'inconclusive_required_coverage'
    elif required_review:
        gate = 'human_review_required'
    else:
        gate = 'bounded_evidence_ready_for_human_review'
    data = {'schema': SCHEMA, 'inputs': input_rows,
            'scope': {'assessments': len(input_rows), 'distinct_generations': len(generations),
                      'distinct_policies': len(policies), 'distinct_source_scopes': len(source_scopes),
                      'comparable_current_source_and_policy': not incomparable},
            'review_tasks': sorted(tasks.values(), key=lambda x: (x['priority'], x['kind'], x['id'])),
            'gate': {'status': gate, 'open_finding_occurrences': open_finding_count,
                     'distinct_verified_findings': len(all_current_findings),
                     'remediation_review_obligations': required_review,
                     'required_coverage_incomplete': incomplete,
                     'release_authorized': False, 'reviewer_identity_authenticated': False,
                     'whole_repository_correctness_certified': False},
            'limitations': [
                'Only the explicitly supplied and natively verified AE-06 assessments are covered.',
                'Matching current generations do not prove policy exhaustiveness across the repository.',
                'A bounded absence candidate is not proof of remediation causality or closure.',
                'Review priorities are workflow categories, not defect likelihood or risk probabilities.',
                'No release approval, reviewer authentication, or whole-repository correctness claim is issued.']}
    data['portfolio_sha256'] = sha(canonical(data))
    return data


def verify_portfolio(record: dict, entries: list[dict]) -> dict:
    if not isinstance(record, dict) or record.get('schema') != SCHEMA:
        raise ValueError('Unexpected AE-07 portfolio schema')
    digest = record.get('portfolio_sha256')
    if not isinstance(digest, str) or sha(canonical({k: v for k, v in record.items()
                                                  if k != 'portfolio_sha256'})) != digest:
        raise ValueError('AE-07 portfolio digest mismatch')
    independent = build_portfolio(entries)
    if canonical(independent) != canonical(record):
        raise ValueError('AE-07 portfolio does not agree with reverified input publications')
    return {'portfolio_sha256': digest, 'status': record['gate']['status'],
            'review_tasks': len(record['review_tasks']),
            'verified_from_native_evidence': True, 'release_authorized': False}
