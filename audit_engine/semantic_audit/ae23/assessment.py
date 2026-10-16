"""Two-stage, scope-safe, abstention-complete assessment of offline Git cases.

Stage A admits exact commit-tree source and computes observations without labels.
Stage B reads independent reviewer statements and scores only consensual cases.
Neither stage executes target code or authenticates remote Git hosting identity.
"""
from __future__ import annotations

import io
import tokenize
from collections import defaultdict
from pathlib import Path
from typing import Mapping

from audit_engine.semantic_audit.ae01.publication import canonical
from audit_engine.semantic_audit.ae15.flow import analyze_snapshot
from audit_engine.semantic_audit.ae22.evaluate import _observation
from audit_engine.semantic_audit.ae23.admission import admit, read_canonical, sha

REVIEW_SCHEMA = 'ae23/reviewer_labels/v1'
PREDICTION_SCHEMA = 'ae23/static_predictions/v1'
REPORT_SCHEMA = 'ae23/offline_external_assessment/v1'
ALLOWED = {'possible_unbound', 'no_unbound_signal', 'unknown', 'out_of_scope'}


def _static(source: bytes, path: str, variable: str | None, eligible: bool) -> dict:
    if not eligible:
        return {'status': 'out_of_scope', 'basis': 'Static semantics outside declared AE-15 scope'}
    try:
        enc, _ = tokenize.detect_encoding(io.BytesIO(source).readline)
        source.decode(enc)
        from audit_engine.semantic_audit.ae01.source import SCHEMA as INVENTORY_SCHEMA
        manifest = {'schema': INVENTORY_SCHEMA, 'source_root': '.', 'files': [
            {'path': path, 'status': 'included', 'sha256': sha(source),
             'bytes': len(source), 'encoding': enc}], 'summary': {'included': 1, 'error': 0}}
        flow, _ = analyze_snapshot({path: source}, manifest, max_total_points=5000,
                                   max_points_per_scope=2000, max_iterations=2500)
        result = _observation(flow, path, variable, eligible=True)
        # A 'no signal' is still not a clean-code verdict; preserve that status.
        return {'status': result['status'], 'basis': result.get('basis', 'AE-15 may-flow observation'),
                'analysis_completeness': flow['assurance'],
                'source_sha256': sha(source)}
    except (ValueError, SyntaxError, UnicodeError, LookupError, RecursionError) as exc:
        return {'status': 'unknown', 'basis': 'Bounded static evaluation incomplete',
                'incomplete_exception': type(exc).__name__, 'source_sha256': sha(source)}


def predict(lock_path: Path | str, repositories: Mapping[str, Path | str]) -> dict:
    """Do not read reviewer labels; no code execution, no verified findings."""
    admitted = admit(lock_path, repositories)
    rows = []
    for case in admitted['cases']:
        cid = case['case_id']
        rows.append({'case_id': cid, 'split': case['split'], 'family': case['family'],
                     'scope': case['scope'], 'source_bindings': case['source_bindings'],
                     'faulty': _static(admitted['sources'][cid+'_faulty.py'], cid+'_faulty.py',
                                       case['signal_variable'], case['scope']=='bounded_static'),
                     'correct': _static(admitted['sources'][cid+'_correct.py'], cid+'_correct.py',
                                        case['signal_variable'], case['scope']=='bounded_static')})
    return {'schema': PREDICTION_SCHEMA, 'lock_sha256': admitted['lock_sha256'],
            'source_authority': admitted['authority'],
            'analyzer': 'ae15/bounded_may_flow_observation_not_runtime_proof',
            'benchmark_source_execution': 'NOT_PERFORMED',
            'label_access_during_prediction': 'NOT_READ',
            'upstream_origin_authenticated': False, 'verified_findings': [],
            'rows': rows}


def validate_reviews(document: dict, lock_sha256: str, case_ids: set[str]) -> dict[str, dict]:
    if (not isinstance(document, dict) or set(document) != {'schema', 'lock_sha256', 'reviews'}
            or document['schema'] != REVIEW_SCHEMA or document['lock_sha256'] != lock_sha256
            or not isinstance(document['reviews'], list)):
        raise ValueError('Invalid or stale independent-review document')
    grouped = defaultdict(list)
    for rev in document['reviews']:
        if not isinstance(rev, dict) or set(rev) != {'case_id', 'reviewer_id', 'faulty',
                                                     'correct', 'rationale', 'prediction_blinded'}:
            raise ValueError('Malformed reviewer statement')
        if rev['case_id'] not in case_ids:
            raise ValueError('Review refers to unknown case')
        if (not isinstance(rev['reviewer_id'], str) or not rev['reviewer_id'].strip()
                or len(rev['reviewer_id']) > 90 or not isinstance(rev['rationale'], str)
                or not 12 <= len(rev['rationale']) <= 1500):
            raise ValueError('Missing reviewer identity or substantive rationale')
        if rev['faulty'] not in {'defective', 'not_defective', 'uncertain'} or rev['correct'] not in {
            'defective', 'not_defective', 'uncertain'} or type(rev['prediction_blinded']) is not bool:
            raise ValueError('Invalid reviewer labels or blinding declaration')
        if any(x['reviewer_id'] == rev['reviewer_id'] for x in grouped[rev['case_id']]):
            raise ValueError('Duplicate reviewer identity within a case')
        grouped[rev['case_id']].append(rev)
    decisions = {}
    for cid in sorted(case_ids):
        reviews = grouped.get(cid, [])
        if len(reviews) < 2:
            status = 'insufficient_review'
        elif (len(reviews) != 2 or any(not r['prediction_blinded'] for r in reviews)):
            status = 'unverified_review_independence'
        elif any((r['faulty'],r['correct']) != ('defective','not_defective') for r in reviews):
            status = 'review_disagreement_or_uncertain'
        else:
            status = 'two_reviewer_agreement_self_attested'
        decisions[cid] = {'status': status, 'reviewer_count': len(reviews),
                          'independence_authenticated': False,
                          'reviewer_ids': [r['reviewer_id'] for r in reviews]}
    return decisions


def score(predictions: dict, reviews: dict) -> dict:
    """Evaluation is descriptive and restricted to two-reviewer-agreed pairs."""
    if (not isinstance(predictions, dict) or predictions.get('schema') != PREDICTION_SCHEMA
            or predictions.get('source_authority') !=
            'locally_supplied_git_objects_integrity_checked__upstream_origin_not_authenticated'
            or predictions.get('verified_findings') != []
            or predictions.get('upstream_origin_authenticated') is not False
            or predictions.get('benchmark_source_execution') != 'NOT_PERFORMED'
            or predictions.get('label_access_during_prediction') != 'NOT_READ'):
        raise ValueError('Predictions have invalid assurance or authority')
    rows = predictions.get('rows')
    if not isinstance(rows, list) or not rows:
        raise ValueError('Prediction set is empty')
    ids = [r.get('case_id') for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate prediction case ID')
    for r in rows:
        if r.get('split') not in {'development', 'holdout'} or r.get('scope') not in {
            'bounded_static', 'unsupported_semantics'}:
            raise ValueError('Invalid case protocol on prediction')
        for role in ('faulty', 'correct'):
            obs = r.get(role)
            if not isinstance(obs, dict) or obs.get('status') not in ALLOWED:
                raise ValueError('Invalid or missing source observation')
            if (r['scope'] == 'unsupported_semantics') != (obs['status'] == 'out_of_scope'):
                raise ValueError('Mismatch between declared semantic scope and result')
            binding = r.get('source_bindings', {}).get(role, {})
            if (binding.get('sha256') != obs.get('source_sha256', binding.get('sha256'))
                    or binding.get('git_tree_binding') != 'verified'
                    or binding.get('upstream_owner_authenticated') is not False):
                raise ValueError('Prediction source linkage or provenance mismatch')
    decisions = validate_reviews(reviews, predictions['lock_sha256'], set(ids))
    metrics = {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0, 'unknown_defective': 0,
               'unknown_control': 0, 'out_of_scope_defective': 0, 'out_of_scope_control': 0}
    by_split, by_family = defaultdict(list), defaultdict(list)
    results = []
    for r in rows:
        decision = decisions[r['case_id']]
        eligible = decision['status'] == 'two_reviewer_agreement_self_attested'
        if eligible:
            for role, defect in (('faulty', True), ('correct', False)):
                status = r[role]['status']
                if status == 'out_of_scope':
                    key = 'out_of_scope_defective' if defect else 'out_of_scope_control'
                elif status == 'unknown':
                    key = 'unknown_defective' if defect else 'unknown_control'
                elif status == 'possible_unbound':
                    key = 'tp' if defect else 'fp'
                else:
                    key = 'fn' if defect else 'tn'
                metrics[key] += 1
        item = {'case_id': r['case_id'], 'split': r['split'], 'family': r['family'],
                'review_status': decision['status'], 'included_in_provisional_metrics': eligible,
                'faulty_signal': r['faulty']['status'], 'correct_signal': r['correct']['status']}
        results.append(item)
        by_split[r['split']].append(item)
        by_family[r['family']].append(item)
    total = len(rows) * 2
    decided = sum(metrics[k] for k in ('tp', 'fp', 'fn', 'tn'))
    unknown = metrics['unknown_defective'] + metrics['unknown_control']
    unsupported = metrics['out_of_scope_defective'] + metrics['out_of_scope_control']
    excluded = total - decided - unknown - unsupported
    if min(decided, unknown, unsupported, excluded) < 0 or decided+unknown+unsupported+excluded != total:
        raise ValueError('Benchmark denominator lost cases')
    def summarize(items):
        return {'pairs':len(items), 'adjudicated_pairs':sum(i['included_in_provisional_metrics'] for i in items),
                'not_adjudicated_pairs':sum(not i['included_in_provisional_metrics'] for i in items)}
    return {'schema': REPORT_SCHEMA, 'prediction_sha256': sha(canonical(predictions)),
            'review_sha256': sha(canonical(reviews)), 'lock_sha256':predictions['lock_sha256'],
            'cases': results, 'case_count':len(rows), 'sample_count':total,
            'provisional_two_reviewer_metrics':metrics,
            'decided_samples':decided, 'unknown_samples':unknown, 'unsupported_samples':unsupported,
            'unadjudicated_samples':excluded,
            'sample_coverage':decided / total,
            'by_split':{k:summarize(v) for k,v in sorted(by_split.items())},
            'by_family':{k:summarize(v) for k,v in sorted(by_family.items())},
            'behavioral_oracle_reproduction': 'NOT_RUN',
            'upstream_origin_authenticated':False,
            'independent_reviewer_identity_authenticated':False,
            'heldout_blinding_authenticated':False,
            'verified_findings':[], 'verified_root_causes':[],
            'claim_status':'NO_EXTERNAL_GENERALIZATION_OR_VERIFIED_BUGS',
            'limitations':[
                'Git-tree membership and hashes do not authenticate repository ownership or original upstream provenance',
                'Two distinct reviewer IDs and asserted prediction blinding are not independently authenticated',
                'Source programs are never executed; no independent behavioral bug reproduction occurred',
                'A missing static warning is never a verified clean-code verdict',
                'Metrics on agreed reviewer labels are descriptive, not independent defect-detection accuracy',
                'Holdout split is enforced for byte reuse, but developer access and sampling independence are unproven',
                'Unknown, unsupported and unadjudicated samples remain in the complete denominator']}


def evaluate(lock_path: Path | str, repos: Mapping[str, Path | str], review_path: Path | str) -> dict:
    pred = predict(lock_path, repos)
    rev, _ = read_canonical(review_path)
    return score(pred, rev)


def replay_equivalent(lock_path: Path | str, repos: Mapping[str, Path | str],
                      review_path: Path | str, claimed: dict) -> bool:
    return claimed == evaluate(lock_path, repos, review_path)
