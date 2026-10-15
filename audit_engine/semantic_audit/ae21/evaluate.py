"""AE-21/G9.23 externally motivated, bounded behavioral-effectiveness pilot.

Not an arbitrary source executor, sandbox, root-cause finder, or production
accuracy benchmark. Requires explicit consent for executing exactly pinned
curator-reviewed fixture files in a manually dispatched trusted GitHub job.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
from pathlib import Path

from audit_engine.semantic_audit.ae01.publication import canonical, _no_symlink_components
from audit_engine.semantic_audit.ae01.source import inventory
from audit_engine.semantic_audit.ae15.flow import analyze_snapshot

SCHEMA = 'ae21/curated_external_pilot_evaluation/v1'
# Exact approved bytes, pinned IN THE EVALUATOR, not provided by an editable label.
PINNED = {
    'QUIXBUGS_LICENSE.txt':'8af72d18a9636ae13ea5a351fa94c91e39b72ca247db600a796ede382862bd94',
    'REFERENCE.json':'414525a9deda46aa23ba0f044692f0224ab036d3afc26ec26e4e0cd11368bac5',
    'branch_unbound_correct.py':'eddda52a06cc82068f18deb5eb603e237c0c7853d23f22afe715f85a5fbcaadc',
    'branch_unbound_faulty.py':'e4c4f3984f6874a7537c286afdef83e97f4adca25e8335fe3dff1f095fa16a70',
    'loop_unbound_correct.py':'29c439f092300dcb299a0e1a0856eca3a144f257eb23d50edcccd775d4db7d78',
    'loop_unbound_faulty.py':'513113bc7ef88090b513427fc6f18721eeb53a258dd32ead2def7b095da29312',
    'quixbugs_gcd_correct.py':'b8aa8539f0cd82cca7eb7aa4c4aee884f9684e83517059a2faac7e30eb56b798',
    'quixbugs_gcd_faulty.py':'e045b2bbf4265ca8b2f8200686d9f2a30085c5d55ed1fb6614b355afdc73ff55',
}
MAX_MEMBER_SIZE = 15_000
ALLOWED_CASES = ('QB_GCD', 'SYN_BRANCH', 'SYN_LOOP')
WITNESSES = {
    'gcd_35_21': (35,21), 'gcd_35_0': (35,0),
    'branch_false': (False,), 'branch_true': (True,),
    'loop_empty': ([],), 'loop_nonempty': ([7],),
}


def admit_pilot(root: Path | str) -> dict:
    """Reject a changed fixture, even if its editable reference is rehashed."""
    root = Path(os.path.abspath(root))
    _no_symlink_components(root)
    if not root.is_dir() or not stat.S_ISDIR(root.lstat().st_mode):
        raise ValueError('Pilot reference root must be a real directory')
    observed = {}
    for child in root.iterdir():
        _no_symlink_components(child)
        if not stat.S_ISREG(child.lstat().st_mode):
            raise ValueError('Pilot members must be regular files')
        if child.stat().st_size > MAX_MEMBER_SIZE:
            raise ValueError('Pilot member too large')
        observed[child.name] = hashlib.sha256(child.read_bytes()).hexdigest()
    if observed != PINNED:
        raise ValueError('Pilot reference source or membership differs from code-pinned expectations')
    raw = (root/'REFERENCE.json').read_bytes()
    reference = json.loads(raw)
    if not isinstance(reference,dict) or raw != canonical(reference):
        raise ValueError('Pilot reference must be a canonical JSON object')
    cases = reference.get('cases',[])
    if not isinstance(cases,list) or tuple(x.get('case_id') for x in cases)!=ALLOWED_CASES:
        raise ValueError('Pilot case IDs or order not admitted')
    for case in cases:
        if case.get('defective') not in PINNED or case.get('correct') not in PINNED:
            raise ValueError('Missing reference source')
        if not case['defective'].endswith('.py') or not case['correct'].endswith('.py'):
            raise ValueError('Unsupported reference source')
        if case.get('witness') not in WITNESSES or case.get('control') not in WITNESSES:
            raise ValueError('Unknown behavioral oracle')
    return reference


def _run_trusted_fixture(data: bytes, filename: str, function: str, witness: str) -> dict:
    """Trusted, *approved* fixture evaluation. No OS sandbox; not for uploads."""
    namespace = {'__name__': '__ae21_trusted_fixture__'}
    original_limit = sys.getrecursionlimit()
    try:
        # Bound the intentional QuixBugs infinite recursion without altering
        # the global interpreter setting beyond the duration of this call.
        if filename.startswith('quixbugs_'):
            sys.setrecursionlimit(max(500, min(original_limit, 600)))
        exec(compile(data, filename, 'exec'), namespace, namespace)
        fn = namespace[function]
        try:
            value = fn(*WITNESSES[witness])
        except (RecursionError, UnboundLocalError) as exc:
            return {'kind':'exception','name':type(exc).__name__}
        if value is None or type(value) in (int,bool,str):
            return {'kind':'return','value':value}
        return {'kind':'unsupported_result','type':type(value).__name__}
    finally:
        sys.setrecursionlimit(original_limit)


def _static_signal(report: dict, path: str, variable: str | None) -> dict:
    """Inspect published observation *facts*, not invent verifier receipts."""
    if variable is None:
        return {'status':'out_of_scope','reason':'AE-15 does not verify arithmetic algorithm correctness'}
    selected = []
    for scope in report['scopes']:
        if scope.get('source') != path:
            continue
        for use in scope.get('uses',[]):
            if use.get('name')==variable and use.get('local'):
                selected.append({'line':use['line'],'status':use['status']})
    # A missing use is UNKNOWN, not a clean result.
    if not selected:
        return {'status':'unknown','reason':'No scope-local observed use under the declared name'}
    return {'status':'possible_unbound' if any(u['status']=='possibly_unbound' for u in selected)
            else 'no_unbound_signal', 'uses':selected}


def evaluate_pilot(root: Path | str, *, explicit_trusted_execution: bool = False) -> dict:
    if explicit_trusted_execution is not True:
        raise PermissionError('Curated Python execution requires explicit trusted opt-in')
    root = Path(os.path.abspath(root))
    reference = admit_pilot(root)  # ALL admission checks precede execution.
    manifest, sources = inventory(root)
    if set(sources) != {name for name in PINNED if name.endswith('.py')}:
        raise ValueError('Python source inventory mismatch')
    report, _ = analyze_snapshot(sources,manifest)
    metrics = {'tp':0,'fp':0,'fn':0,'tn':0,'unknown':0,'out_of_scope_pairs':0}
    reproduced = 0
    rows=[]
    for case in reference['cases']:
        defect,correct = case['defective'],case['correct']
        bad = _run_trusted_fixture(sources[defect],defect,case['function'],case['witness'])
        good = _run_trusted_fixture(sources[correct],correct,case['function'],case['witness'])
        bad_control = _run_trusted_fixture(sources[defect],defect,case['function'],case['control'])
        good_control = _run_trusted_fixture(sources[correct],correct,case['function'],case['control'])
        # Gold is independently specified in REFERENCE, not inferred from AE-15.
        expected=case['expected']
        faithful=(bad==expected['defective'] and good==expected['correct']
                  and bad_control==expected['control'] and good_control==expected['control'])
        reproduced += int(faithful)
        bad_signal=_static_signal(report,defect,case['variable'])
        good_signal=_static_signal(report,correct,case['variable'])
        if case['intended_static_scope']=='out_of_scope_algorithmic_correctness':
            metrics['out_of_scope_pairs']+=1
        else:
            for expected_defective,signal in ((True,bad_signal),(False,good_signal)):
                if signal['status'] in ('unknown','out_of_scope'):
                    metrics['unknown']+=1
                elif expected_defective:
                    metrics['tp' if signal['status']=='possible_unbound' else 'fn']+=1
                else:
                    metrics['fp' if signal['status']=='possible_unbound' else 'tn']+=1
        rows.append({'case_id':case['case_id'],'category':case['category'],
                     'oracle_reproduced':faithful,'observed_defective':bad,
                     'observed_correct':good,'observed_control':bad_control,
                     'defective_static_signal':bad_signal,'correct_static_signal':good_signal,
                     'static_scope':case['intended_static_scope'],
                     'source_sha256':{p:PINNED[p] for p in (defect,correct)}})
    return {'schema':SCHEMA,'pilot_case_count':len(rows),'external_source_pairs':1,
            'synthetic_pairs':2,'oracle_reproduced_pairs':reproduced,
            'pilot_gate':'reference_oracles_reproduced' if reproduced==len(rows) else 'reference_oracle_failure',
            'source_authority':'one QuixBugs MIT-licensed curated semantic transcription; not upstream byte-authenticated; two local synthetic controls',
            'analysis_authority':'AE-15 bounded possible-unbound observations only; not verified findings',
            'metrics_scope':'only two synthetic in-scope defect/control pairs; external algorithmic defect excluded from supported detection denominator',
            'supported_scope_confusion':metrics,'graph_fingerprint':report['graph_fingerprint'],
            'static_analysis_completeness':report['assurance'],
            'verified_findings':[],'verified_root_causes':[], 'cases':rows,
            'limitations':['This is a feasibility pilot, NOT a statistically valid held-out benchmark',
                           'External source is curator-transcribed from QuixBugs and not commit-byte-authenticated',
                           'QuixBugs is a repair benchmark; this is not evidence of root-cause detection on real repositories',
                           'Tests execute only exact code-pinned, manually approved Python fixtures with no OS isolation',
                           'Passing behavioral oracle reproduction does not imply auditor detection effectiveness',
                           'No calibrated uncertainty, no independent blinded human adjudication, no verified audit finding'],
            }


def replay_equivalent(root: Path | str, supplied: dict, *, explicit_trusted_execution: bool = False) -> bool:
    """Replay exactly, without trusting a user-supplied result or its digest."""
    return supplied == evaluate_pilot(root,explicit_trusted_execution=explicit_trusted_execution)
