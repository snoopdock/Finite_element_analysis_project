"""AE-18: fixed-label evaluation of the AE-16 -> AE-17 operational slice.

The oracle labels are committed, byte-pinned, and never synthesized by the
analyzers being evaluated. These are *controlled synthetic* examples, not
externally adjudicated historical incidents or verified GitHub execution data.
No repository source or declared command is executed by this module.
"""
from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any

from audit_engine.semantic_audit.ae01.publication import canonical, sha, _no_symlink_components
from audit_engine.semantic_audit.ae16 import build_report, publish_observation, verify_observation
from audit_engine.semantic_audit.ae17 import build_investigation, publish_investigation, verify_investigation

SCHEMA = 'ae18/operational_effectiveness_evaluation/v1'
MANIFEST_SCHEMA = 'ae18/reference_manifest/v1'
LABEL_SCHEMA = 'ae18/independent_reference_labels/v1'
MAX_CASES = 48
MAX_FILES = 256
MAX_BYTES = 6_000_000
MAX_FILE_BYTES = 1_000_000
VALID_CASE = re.compile(r'^[A-Z][A-Za-z0-9_]{2,79}$')
HEX64 = re.compile(r'^[0-9a-f]{64}$')


def _read_canonical(path: Path) -> dict:
    _no_symlink_components(path)
    if not path.is_file() or not stat.S_ISREG(path.stat().st_mode) or path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError('Missing, oversized or nonregular corpus document')
    data = path.read_bytes()
    def strict_pairs(pairs):
        doc = {}
        for k,v in pairs:
            if k in doc: raise ValueError('Duplicate JSON property')
            doc[k] = v
        return doc
    result = json.loads(data, object_pairs_hook=strict_pairs)
    if not isinstance(result, dict) or data != canonical(result):
        raise ValueError('Reference document must be a canonical JSON object')
    return result


def _admit(root: Path) -> tuple[dict,dict]:
    """Reject unlisted files, modified labels, links and unsafe members."""
    root = Path(os.path.abspath(root))
    _no_symlink_components(root)
    if not root.is_dir(): raise ValueError('Corpus root must be a directory')
    manifest = _read_canonical(root / 'MANIFEST.json')
    if set(manifest) != {'schema','cases','sha256','assurance'} or manifest['schema'] != MANIFEST_SCHEMA:
        raise ValueError('Unsupported reference corpus manifest')
    ids = manifest['cases']
    if (not isinstance(ids,list) or not 1<=len(ids)<=MAX_CASES or ids!=sorted(set(ids)) or
        any(not isinstance(c,str) or not VALID_CASE.fullmatch(c) for c in ids)):
        raise ValueError('Invalid reference case IDs')
    digests = manifest['sha256']
    if not isinstance(digests,dict) or len(digests)>MAX_FILES:
        raise ValueError('Corpus size or digest inventory invalid')
    names=set()
    total=0
    for path in root.rglob('*'):
        if path.is_symlink():raise ValueError('Reference corpus symlink rejected')
        if path.is_dir():continue
        if not stat.S_ISREG(path.stat().st_mode): raise ValueError('Nonregular reference artifact')
        rel=path.relative_to(root).as_posix()
        if any(c in rel for c in ('\\','\x00')) or any(c in ('','..','.') for c in rel.split('/')):
            raise ValueError('Unsafe corpus path')
        names.add(rel)
        size=path.stat().st_size
        if size>MAX_FILE_BYTES:raise ValueError('Oversized reference artifact')
        total+=size
        if total>MAX_BYTES:raise ValueError('Corpus byte budget exceeded')
    if names!=set(digests)|{'MANIFEST.json'}:raise ValueError('Corpus has missing or unlisted member')
    for name,digest in digests.items():
        if (not isinstance(name,str) or name.startswith('/') or ':' in name or '\\' in name or
            any(p in ('','.','..') for p in name.split('/')) or
            not isinstance(digest,str) or not HEX64.fullmatch(digest)):
            raise ValueError('Malformed corpus evidence binding')
        if sha((root / name).read_bytes())!=digest:raise ValueError('Corpus bytes or labels changed')
    labels = _read_canonical(root/'labels.json')
    if set(labels)!={'schema','scope','oracle_authority','cases'} or labels['schema']!=LABEL_SCHEMA:
        raise ValueError('Unsupported independent reference labels')
    if labels['oracle_authority']!='manually_authored_controls_not_externally_adjudicated':
        raise ValueError('Inaccurate reference-label authority')
    if set(labels['cases'])!=set(ids):raise ValueError('Missing/extra expected case labels')
    for name in ids:
        expected_files = {f'cases/{name}/declaration.json'}
        evidence_prefix=f'cases/{name}/evidence/'
        present = {n for n in digests if n==f'cases/{name}/declaration.json' or n.startswith(evidence_prefix)}
        if not expected_files.issubset(present):raise ValueError('Missing reference declaration')
        _read_canonical(root/f'cases/{name}/declaration.json')
        label=labels['cases'][name]
        if set(label)!={'expected_issues','rationale'} or not isinstance(label['rationale'],str):
            raise ValueError('Invalid independent label')
        observations=label['expected_issues']
        if (not isinstance(observations,list) or any(not isinstance(v,dict) or set(v)!={'kind','subject'} or
             not isinstance(v['kind'],str) or not isinstance(v['subject'],str) for v in observations)):
            raise ValueError('Invalid expected issue format')
        if observations!=sorted(observations,key=lambda r:(r['kind'],r['subject'])) or len(observations)!=len({(v['kind'],v['subject']) for v in observations}):
            raise ValueError('Duplicate or unsorted independent labels')
    return manifest,labels


def classify(expected: list[dict],observed: list[dict]) -> dict:
    """Pure exact-identity oracle, independent of the analyzer implementation."""
    def normalize(records):
        if not isinstance(records,list) or any(not isinstance(v,dict) or
             set(v)!={'kind','subject'} or not isinstance(v['kind'],str) or
             not isinstance(v['subject'],str) for v in records):
            raise ValueError('Ill-formed observation comparison')
        ids=[(v['kind'],v['subject']) for v in records]
        if len(ids)!=len(set(ids)):raise ValueError('Duplicate issue identity')
        return set(ids)
    truth=normalize(expected);actual=normalize(observed)
    def rows(items):return [{'kind':a,'subject':b} for a,b in sorted(items)]
    return {'true_positive':len(truth&actual),'false_positive':len(actual-truth),
            'false_negative':len(truth-actual),'expected':rows(truth),'observed':rows(actual),
            'unexpected':rows(actual-truth),'missing':rows(truth-actual),
            'exact_match':truth==actual,'clean_control':not truth,
            'false_clean':bool(truth) and not bool(actual),'false_alarm':not truth and bool(actual)}


def evaluate_corpus(corpus_root:Path|str) -> dict:
    root=Path(os.path.abspath(corpus_root))
    manifest,labels=_admit(root)
    cases=[]
    for case_id in manifest['cases']:
        where=root/'cases'/case_id
        declaration=where/'declaration.json'
        evidence=where/'evidence'
        with tempfile.TemporaryDirectory(prefix='ae18-controlled-eval-') as directory:
            out=Path(directory)
            ae16_path=out/'ae16';ae17_path=out/'ae17'
            source=publish_observation(declaration,evidence,ae16_path)
            if verify_observation(declaration,evidence,ae16_path)!=source:
                raise ValueError('AE-16 independent replay changed')
            evaluation,graph=build_report(declaration,evidence)
            investigation=publish_investigation(declaration,evidence,ae16_path,ae17_path)
            if verify_investigation(declaration,evidence,ae16_path,ae17_path)!=investigation:
                raise ValueError('AE-17 independent replay changed')
            plan=build_investigation(declaration,evidence,ae16_path)
            # These claims remain unverified regardless of exact reference agreement.
            if (evaluation['verified_findings'] or plan['verified_findings'] or plan['verified_root_causes'] or
                plan['epistemic_status']!='investigation_hypotheses_only' or
                evaluation['source_authority']!='untrusted_execution_declaration_not_github_authenticated'):
                raise ValueError('Unauthorized authority promotion in evaluation')
            comparison=classify(labels['cases'][case_id]['expected_issues'],evaluation['issues'])
            expected_assurance=('incomplete_or_inconsistent' if labels['cases'][case_id]['expected_issues']
                                else 'consistent_declared_observations_unattested')
            assurance_matches=(evaluation['assurance']==expected_assurance)
            selected={(v['issue']['kind'],v['issue']['subject']) for v in plan['cases']}
            actual={(v['kind'],v['subject']) for v in evaluation['issues']}
            plan_complete=bool(selected==actual and not plan['truncated'] and
                               all(v['disposition']=='unresolved_requires_independent_verification' and
                               v['alternatives'] and all(a['epistemic_status']=='unverified_possible_explanation'
                                for a in v['alternatives']) for v in plan['cases']))
            cases.append({'id':case_id,'comparison':comparison,'source_assurance':evaluation['assurance'],
                          'source_generation':source['generation'],
                          'investigation_generation':investigation['generation'],
                          'investigation_covers_all_observed_issues':plan_complete,
                          'assurance_matches_independent_expected_status':assurance_matches,
                          'hypotheses_only':True})
    tp=sum(c['comparison']['true_positive'] for c in cases)
    fp=sum(c['comparison']['false_positive'] for c in cases)
    fn=sum(c['comparison']['false_negative'] for c in cases)
    clean=sum(c['comparison']['clean_control'] for c in cases)
    correct_clean=sum(c['comparison']['clean_control'] and c['comparison']['exact_match'] for c in cases)
    exact=sum(c['comparison']['exact_match'] for c in cases)
    # No denominator -> null, never fabricate a perfect precision or recall.
    precision=tp/(tp+fp) if tp+fp else None
    recall=tp/(tp+fn) if tp+fn else None
    gate=(fp==0 and fn==0 and exact==len(cases) and
          all(c['investigation_covers_all_observed_issues'] and
              c['assurance_matches_independent_expected_status'] for c in cases))
    return {'schema':SCHEMA,'scope':'controlled_synthetic_AE16_AE17_operational_slice_only',
            'reference_authority':'committed_pinned_manual_labels_not_external_ground_truth',
            'source_authority':'supplied_fixture_bytes_not_authenticated_runtime',
            'verified_findings':[],'verified_root_causes':[],
            'corpus_manifest_sha256':sha((root/'MANIFEST.json').read_bytes()),
            'labels_sha256':manifest['sha256']['labels.json'],
            'metrics':{'case_count':len(cases),'exact_case_matches':exact,
                       'true_positive':tp,'false_positive':fp,'false_negative':fn,
                       'precision':precision,'recall':recall,'clean_controls':clean,
                       'correct_clean_controls':correct_clean,'false_clean_cases':sum(c['comparison']['false_clean'] for c in cases),
                       'false_alarm_cases':sum(c['comparison']['false_alarm'] for c in cases)},
            'candidate_gate':'pass_controlled_reference_only' if gate else 'fail_controlled_reference',
            'limitations':['No real incident ground truth or independent causal verification',
                'No authenticated GitHub execution telemetry',
                'No Python call-resolution or test-oracle-mutation effectiveness claim',
                'No cross-repository or C01-C15 completion claim'],
            'cases':cases}
