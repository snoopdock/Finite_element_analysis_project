"""AE-06: conservative, replayable remediation and regression assessment.

Every input is a sealed AE-01/04/05 publication independently verified by its
native verifier. An absent finding is NOT proof that underlying behavior was
repaired: matching policy, source scope, and executed source rule are required.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from audit_engine.semantic_audit.ae01.publication import canonical, sha
from audit_engine.semantic_audit.ae02.snapshots import load_generation, VerifiedGeneration
from audit_engine.semantic_audit.ae04 import verify_publication as verify_campaign_publication
from audit_engine.semantic_audit.ae05 import verify_review_publication
from audit_engine.semantic_audit.ae05.publication import _stored as read_verified_review
from audit_engine.semantic_audit.verification.immutable_payload import thaw

SCHEMA = 'ae06/remediation_assessment/v1'


def _manifest(g: VerifiedGeneration) -> dict[str, str]:
    return {r['path']: r['sha256'] for r in g.manifest['files'] if r['status'] == 'included'}


def _findings(g: VerifiedGeneration) -> list[dict]:
    return thaw(g.report['findings'])


def _imports(g: VerifiedGeneration) -> dict[str, dict]:
    return {row['id']: thaw(row) for row in g.facts['imports']}


def _classification_equal(a: VerifiedGeneration, b: VerifiedGeneration) -> bool:
    # Both the rule bytes and the operational (lifecycle/exclusion/parser) scope
    # must agree. SHA of the YAML rule alone is NOT a sufficient policy identity.
    return canonical(thaw(a.policy)) == canonical(thaw(b.policy))


def _source_executed(g: VerifiedGeneration, file: str) -> bool:
    from audit_engine.semantic_audit.ae01.source import module_name
    module = module_name(file)
    return any(e['source_module'] == module and e['rule_execution']['reason'] == 'executed'
               and e['rule_execution']['obligations'] and
               len(e['rule_execution']['obligations']) == len(e['rule_execution']['receipts'])
               for e in g.executions)


def _signature(entry: dict, imp: dict) -> tuple[str, str, str]:
    return entry['finding']['rule_id'], imp['file'], imp['target']


def _origin_review_state(review: dict, finding_id: str) -> str:
    # AE-05 records are human assertions, not authenticated signatures.
    # A 'dispute' cannot be treated as remediation authorization.
    obligations = {o['id']: o for o in review['packet']['obligations']}
    matching = [key for key, row in obligations.items()
                if row['kind'] == 'source_task' and finding_id in row['evidence_refs']]
    if not matching:
        return 'not_recorded'
    last = {}
    for event in review['events']:
        last[event['obligation_id']] = event['action']
    return 'requires_action_recorded' if all(last.get(k) == 'requires_action' for k in matching) else 'review_unresolved'


def _comparable(g: VerifiedGeneration, other: VerifiedGeneration, source_file: str,
                old_target_files: tuple[str, ...] = ()) -> tuple[bool, list[str]]:
    reasons = []
    if not _classification_equal(g, other):
        reasons.append('policy_or_classification_changed')
    if other.report['assurance_completeness'] != 'complete_within_declared_scope':
        reasons.append('current_source_or_policy_coverage_incomplete')
    if source_file not in _manifest(other):
        reasons.append('source_module_not_in_current_scope')
    elif not _source_executed(other, source_file):
        reasons.append('source_rule_not_executed_on_current_dependency')
    if any(candidate in _manifest(g) and candidate not in _manifest(other) for candidate in old_target_files):
        reasons.append('previous_target_module_left_audit_scope')
    return not reasons, reasons


def _historical_clear(g: VerifiedGeneration, history: list[VerifiedGeneration],
                      source_file: str, sig: tuple[str, str, str],
                      old_target_files: tuple[str, ...]) -> bool:
    for prior in history:
        eligible, _ = _comparable(g, prior, source_file, old_target_files)
        if not eligible:
            continue
        prior_imp = _imports(prior)
        previous_signatures = {_signature(row, prior_imp[row['witness']['occurrence_id']])
                               for row in _findings(prior)}
        if sig not in previous_signatures:
            return True
    return False


def build_assessment(*, origin_before: Path | str, flagged_output: Path | str,
                     current_output: Path | str, origin_campaign: Path | str,
                     origin_review: Path | str, followup_campaign: Path | str,
                     history_outputs: tuple[Path | str, ...] = (),
                     history_campaigns: tuple[Path | str, ...] = (),
                     origin_mutation_root: Path | None = None,
                     followup_mutation_root: Path | None = None,
                     replay_origin_mutation: bool = False,
                     replay_followup_mutation: bool = False) -> dict:
    """Assess one review-to-followup transition; historical inputs are verified.

    A closure candidate is only a bounded absence observation, not a causal
    remediation proof, official waiver, authenticated approval, or deployment
    readiness judgment.
    """
    first = load_generation(origin_before)
    flagged = load_generation(flagged_output)
    current = load_generation(current_output)
    original_receipt = verify_campaign_publication(
        origin_campaign, before_output=origin_before, after_output=flagged_output,
        mutation_root=origin_mutation_root, replay_mutation=replay_origin_mutation)
    reviewed_receipt = verify_review_publication(
        origin_review, campaign_output=origin_campaign,
        before_output=origin_before, after_output=flagged_output,
        mutation_root=origin_mutation_root, replay_mutation=replay_origin_mutation)
    review = read_verified_review(Path(origin_review).absolute())
    if review['review_sha256'] != reviewed_receipt['review_sha256']:
        raise ValueError('AE-05 latest review changed between independent verification and evidence loading')
    followup_receipt = verify_campaign_publication(
        followup_campaign, before_output=flagged_output, after_output=current_output,
        mutation_root=followup_mutation_root, replay_mutation=replay_followup_mutation)
    if (review['packet']['previous_generation_id'] != first.snapshot.generation_id or
            review['packet']['current_generation_id'] != flagged.snapshot.generation_id or
            review['packet']['campaign_sha256'] != original_receipt['campaign_sha256']):
        raise ValueError('Original reviewed campaign is not bound to the flagged AE-01 source audit')
    followup_path = Path(followup_campaign) / 'generations' / followup_receipt['generation'] / 'campaign.json'
    from audit_engine.semantic_audit.ae01.publication import _no_symlink_components
    _no_symlink_components(followup_path)
    import json
    followup = json.loads(followup_path.read_bytes())
    if (followup['previous']['generation_id'] != flagged.snapshot.generation_id or
            followup['current']['generation_id'] != current.snapshot.generation_id or
            followup['campaign_sha256'] != followup_receipt['campaign_sha256']):
        raise ValueError('Follow-up campaign does not compare exactly the reviewed and current generations')
    if len(history_outputs) > 32:
        raise ValueError('Historical comparison is bounded to 32 verified generations')
    hist = [load_generation(out) for out in history_outputs]
    if history_outputs and len(history_campaigns) != len(history_outputs) + 1:
        raise ValueError('Reintroduction history requires a sealed campaign for every adjacent generation pair')
    if not history_outputs and history_campaigns:
        raise ValueError('Cannot claim ordered history from a campaign without intermediate generations')
    # Independent AE-04 links prove predecessor/successor adjacency; the
    # caller cannot simply supply arbitrary historical files as chronology.
    chain = [flagged_output, *history_outputs, current_output]
    chain_receipts = []
    for i, path in enumerate(history_campaigns):
        receipt = verify_campaign_publication(path, before_output=chain[i], after_output=chain[i+1])
        chain_receipts.append(receipt['campaign_sha256'])
    ids = [h.snapshot.generation_id for h in hist]
    if len(set(ids)) != len(ids) or any(x in (flagged.snapshot.generation_id,
             current.snapshot.generation_id) for x in ids):
        raise ValueError('Historical generations must be unique and distinct from endpoints')
    old_imp = _imports(flagged)
    new_imp = _imports(current)
    recent_findings = _findings(current)
    recent_signatures = {_signature(row, new_imp[row['witness']['occurrence_id']])
                         for row in recent_findings}
    by_source: dict[str, list[dict]] = {}
    for item in recent_findings:
        by_source.setdefault(item['witness']['source_id'], []).append(item)
    cases = []
    for entry in sorted(_findings(flagged), key=lambda x: x['finding']['finding_id']):
        witness = entry['witness']
        file = witness['source_id']
        imp = old_imp[witness['occurrence_id']]
        signature = _signature(entry, imp)
        review_state = _origin_review_state(review, entry['finding']['finding_id'])
        comparable, reasons = _comparable(flagged, current, file, tuple(imp['candidates']))
        if not comparable:
            status = 'not_assessable'
        elif signature in recent_signatures:
            status = ('reintroduced_violation' if _historical_clear(flagged, hist, file, signature, tuple(imp['candidates']))
                      else 'persistent_violation')
        elif by_source.get(file):
            status = 'changed_violation_open'
        elif _manifest(flagged)[file] == _manifest(current)[file]:
            status = 'not_assessable'
            reasons.append('finding_vanished_without_source_change')
        elif review_state != 'requires_action_recorded':
            status = 'review_required'
            reasons.append('remediation_review_not_recorded')
        else:
            status = 'bounded_absence_candidate'
        rows = by_source.get(file, [])
        record = {'origin_finding_id': entry['finding']['finding_id'],
                  'rule_id': signature[0], 'source_file': file, 'old_target': signature[2],
                  'old_source_sha256': witness['source_sha256'],
                  'current_source_sha256': _manifest(current).get(file),
                  'old_occurrence_id': witness['occurrence_id'],
                  'review_state': review_state, 'status': status,
                  'reasons': sorted(set(reasons)),
                  'current_findings': sorted(x['finding']['finding_id'] for x in rows),
                  'current_source_rule_executed': _source_executed(current, file)}
        record['case_id'] = sha(canonical({k:v for k,v in record.items() if k not in ('status','reasons')}))
        cases.append(record)
    prior_ids = {item['finding']['finding_id'] for item in _findings(flagged)}
    prior_signatures = {_signature(item, old_imp[item['witness']['occurrence_id']])
                        for item in _findings(flagged)}
    genuinely_new_signatures = sorted(recent_signatures - prior_signatures)
    new_findings = sorted(row['finding']['finding_id'] for row in recent_findings
                          if row['finding']['finding_id'] not in prior_ids)
    unsafe = any(c['status'] in ('not_assessable','review_required') for c in cases)
    open_violations = bool(recent_findings)
    if unsafe or current.report['assurance_completeness'] != 'complete_within_declared_scope':
        outcome = 'inconclusive_requires_review'
    elif open_violations:
        outcome = 'verified_violation_requires_action'
    elif cases and all(c['status'] == 'bounded_absence_candidate' for c in cases):
        outcome = 'bounded_absence_candidates_require_human_closure'
    else:
        outcome = 'no_previous_violation_closure_claim'
    assessment = {
        'schema': SCHEMA,
        'inputs': {'origin_before': first.snapshot.to_dict(), 'flagged': flagged.snapshot.to_dict(),
                   'current': current.snapshot.to_dict(),
                   'origin_campaign_sha256': original_receipt['campaign_sha256'],
                   'origin_review_sha256': reviewed_receipt['review_sha256'],
                   'origin_review_journal_head': review['state']['journal_head_sha256'],
                   'followup_campaign_sha256': followup_receipt['campaign_sha256'],
                   'history': [x.snapshot.to_dict() for x in hist],
                   'history_campaign_sha256': chain_receipts},
        'cases': cases, 'new_finding_ids': new_findings,
        'new_dependency_signatures': [dict(rule_id=r, source_file=f, target_module=t)
                                      for r, f, t in genuinely_new_signatures],
        'assurance': {'status': outcome, 'candidate_count': sum(c['status'] == 'bounded_absence_candidate' for c in cases),
                      'open_finding_count': len(recent_findings),
                      'reviewer_identity_authenticated': False,
                      'remediation_causality_proven': False,
                      'global_software_correctness_certified': False},
        'limitations': [
            'Historical adjacency is supported by sealed AE-04 comparisons; wall-clock ordering is not certified.',
            'Candidate absence is limited to the same policy, declared source scope and executed architecture rule.',
            'Source/target deletion, relocation, and runtime-dynamic imports may require separate review.',
            'Human notes do not authenticate identity or waive confirmed findings.',
            'Runtime behavior, semantic equivalence and general software correctness are not proven.']}
    assessment['assessment_sha256'] = sha(canonical(assessment))
    return assessment


def verify_assessment(record: dict, **kwargs) -> dict:
    if not isinstance(record, dict) or record.get('schema') != SCHEMA:
        raise ValueError('Invalid AE-06 assessment schema')
    if record.get('assessment_sha256') != sha(canonical({k:v for k,v in record.items() if k!='assessment_sha256'})):
        raise ValueError('AE-06 assessment content hash mismatch')
    actual = build_assessment(**kwargs)
    if canonical(record) != canonical(actual):
        raise ValueError('AE-06 assessment disagrees with independently verified audit evidence')
    return {'verification': 'rederived_from_ae01_ae04_ae05',
            'assessment_sha256': record['assessment_sha256'],
            'status': record['assurance']['status'], 'cases': len(record['cases']),
            'general_software_correctness_certified': False}
