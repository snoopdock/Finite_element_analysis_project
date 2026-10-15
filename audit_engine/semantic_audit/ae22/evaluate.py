"""AE-22: frozen reference, exact-byte integrity, abstention-aware static evaluation.

Does NOT execute analyzed source; does NOT authenticate upstream sources; does NOT
produce verifier receipts, code defect proofs, or root-cause findings.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import stat
from pathlib import Path

from audit_engine.semantic_audit.ae01.publication import canonical, _no_symlink_components
from audit_engine.semantic_audit.ae01.source import inventory
from audit_engine.semantic_audit.ae15.flow import analyze_snapshot
from audit_engine.semantic_audit.ae22.pins import PINNED_MEMBERS

SCHEMA='ae22/scoped_effectiveness_report/v1'
REFERENCE_SCHEMA='ae22/casebook_labels/v1'
MAX_MEMBER_BYTES=25_000
MAX_CASES=64


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_file(path: Path) -> dict:
    b=path.read_bytes()
    obj=json.loads(b)
    if not isinstance(obj,dict) or canonical(obj)!=b:
        raise ValueError(f'Noncanonical reference document: {path.name}')
    return obj


def admit_casebook(root: Path | str) -> tuple[dict,dict,dict[str,bytes]]:
    """Every byte and member is code-pinned. No reference-derived hash trust."""
    root=Path(os.path.abspath(root))
    _no_symlink_components(root)
    if not root.is_dir() or not stat.S_ISDIR(root.lstat().st_mode):
        raise ValueError('Reference root must be a real directory')
    contents={}
    for p in root.iterdir():
        _no_symlink_components(p)
        if not stat.S_ISREG(p.lstat().st_mode) or p.stat().st_size>MAX_MEMBER_BYTES:
            raise ValueError('Unsupported reference member type or size')
        contents[p.name]=p.read_bytes()
    digest={k:sha256(v) for k,v in contents.items()}
    if digest!=PINNED_MEMBERS:
        raise ValueError('Reference source, labels, protocol or membership changed')
    labels=_canonical_file(root/'LABELS.json')
    protocol=_canonical_file(root/'PROTOCOL.json')
    if labels.get('schema')!=REFERENCE_SCHEMA or protocol.get('schema')!='ae22/protocol/v1':
        raise ValueError('Unknown benchmark protocol or label schema')
    cases=labels.get('cases')
    if not isinstance(cases,list) or not 1<=len(cases)<=MAX_CASES:
        raise ValueError('Invalid case count')
    seen=set()
    for case in cases:
        if not isinstance(case,dict) or not isinstance(case.get('case_id'),str):
            raise ValueError('Invalid case')
        if case['case_id'] in seen:raise ValueError('Duplicate case ID')
        seen.add(case['case_id'])
        if case.get('scope') not in ('bounded_static','unsupported_semantics'):
            raise ValueError('Invalid declared scope')
        if case.get('adjudication')!='single_curator_not_blind':
            raise ValueError('Unrecognized adjudication level')
        for key in ('faulty','correct'):
            if case.get(key) not in contents or not case[key].endswith('.py'):
                raise ValueError('Unknown case file')
    src={k:v for k,v in contents.items() if k.endswith('.py')}
    referenced={c[k] for c in cases for k in ('faulty','correct')}
    if set(src)!=referenced or len(referenced)!=2*len(cases):
        raise ValueError('Case source member reuse or unreferenced source')
    return labels,protocol,src


def _observation(flow:dict, path:str, name:str|None, *, eligible:bool) -> dict:
    if not eligible:
        return {'status':'out_of_scope','basis':'declared unsupported or nonprogram fault family'}
    if not isinstance(name,str) or not name:
        return {'status':'unknown','basis':'No declared scoped symbol'}
    rows=[]
    incomplete_scopes=[]
    for scope in flow['scopes']:
        if scope.get('source')!=path:continue
        if scope.get('gaps'): incomplete_scopes.extend(scope['gaps'])
        for use in scope.get('uses',[]):
            if use.get('name')==name and use.get('local') is True:
                rows.append({'line':use.get('line'),'status':use.get('status')})
    if not rows:
        return {'status':'unknown','basis':'No matching local use; absence is not verified clean'}
    if any(row['status']=='possibly_unbound' for row in rows):
        return {'status':'possible_unbound','uses':rows,'scope_incomplete':bool(incomplete_scopes)}
    if incomplete_scopes:
        return {'status':'unknown','basis':'Relevant scope has incomplete semantics','uses':rows}
    return {'status':'no_unbound_signal','uses':rows,'basis':'No bounded possible-unbound signal; NOT a verified clean result'}


def _wilson(successes:int, trials:int, z:float=1.959963984540054) -> dict|None:
    """Descriptive Wilson interval on the *observed curated sample*, not population inference."""
    if not trials:return None
    p=successes/trials;den=1+z*z/trials
    ctr=(p+z*z/(2*trials))/den
    half=z*math.sqrt(p*(1-p)/trials+z*z/(4*trials*trials))/den
    return {'fraction':p,'lower':max(0.,ctr-half),'upper':min(1.,ctr+half),
            'interpretation':'descriptive-only:nonrandom-curated-sample'}


def _counts(rows:list[dict]) -> dict:
    count={'tp':0,'fp':0,'fn':0,'tn':0,'unknown_defective':0,'unknown_control':0,
           'out_of_scope_defective':0,'out_of_scope_control':0,'false_clean_claims':0}
    for r in rows:
        for role,truth in (('faulty',True),('correct',False)):
            status=r[role+'_observation']['status']
            if status=='out_of_scope':count['out_of_scope_defective' if truth else 'out_of_scope_control']+=1
            elif status=='unknown':count['unknown_defective' if truth else 'unknown_control']+=1
            elif status=='possible_unbound':count['tp' if truth else 'fp']+=1
            elif status=='no_unbound_signal':count['fn' if truth else 'tn']+=1
            else:raise ValueError('Unsupported analyzer status')
    evaluable=sum(count[k] for k in ('tp','fp','fn','tn'))
    count['all_pairs']=len(rows)
    count['all_samples']=2*len(rows)
    count['scored_samples']=evaluable
    count['abstained_samples']=count['unknown_defective']+count['unknown_control']
    count['unsupported_samples']=count['out_of_scope_defective']+count['out_of_scope_control']
    count['coverage_fraction']=evaluable/count['all_samples'] if count['all_samples'] else None
    count['sensitivity_on_decided']=_wilson(count['tp'],count['tp']+count['fn'])
    count['specificity_on_decided']=_wilson(count['tn'],count['tn']+count['fp'])
    count['false_clean_claims']=0   # API issues NO clean verdicts; missing signal is NOT a verdict.
    return count


def evaluate_casebook(root: Path | str) -> dict:
    """Read-only, static evaluation. No exec, import, subprocess, or source execution."""
    root=Path(os.path.abspath(root))
    labels,protocol,sources=admit_casebook(root)
    manifest,inventory_sources=inventory(root)
    if inventory_sources!=sources:
        raise ValueError('Included Python inventory not identical to admitted reference')
    flow,_graph=analyze_snapshot(sources,manifest,max_total_points=30000)
    rows=[]
    for c in labels['cases']:
        eligible=c['scope']=='bounded_static'
        rows.append({'case_id':c['case_id'],'family':c['family'],'provenance_class':c['origin'],
                     'upstream_byte_authenticated':bool(c['upstream_byte_authenticated']),
                     'adjudication':c['adjudication'],'declared_static_scope':c['scope'],
                     'faulty_source_sha256':sha256(sources[c['faulty']]),
                     'correct_source_sha256':sha256(sources[c['correct']]),
                     'faulty_observation':_observation(flow,c['faulty'],c['signal_variable'],eligible=eligible),
                     'correct_observation':_observation(flow,c['correct'],c['signal_variable'],eligible=eligible)})
    per_family={name:_counts([r for r in rows if r['family']==name]) for name in sorted({r['family'] for r in rows})}
    report={
        'schema':SCHEMA,'casebook_identity':sha256(canonical({'members':PINNED_MEMBERS,'labels':labels,'protocol':protocol})),
        'protocol_sha256':PINNED_MEMBERS['PROTOCOL.json'],'labels_sha256':PINNED_MEMBERS['LABELS.json'],
        'source_sha256':{p:sha256(v) for p,v in sorted(sources.items())},
        'graph_fingerprint':flow['graph_fingerprint'],'analysis_completeness':flow['assurance'],
        'authority':'exploratory_curated_static_observation_only',
        'upstream_byte_authenticated_external_cases':sum(r['upstream_byte_authenticated'] for r in rows if r['provenance_class']!='local_synthetic'),
        'independently_adjudicated_cases':0,'held_out_cases':0,
        'behavioral_oracle_reproduction':'NOT_RUN',
        'claim_prohibition':['no_verified_defects','no_root_causes','no_real_world_accuracy','no_clean_verdicts','no_blind_evaluation'],
        'counts':_counts(rows),'per_family':per_family,'cases':rows,
        'limitations':[
            'Casebook is curated with knowledge of the AE-15 implementation, not sampled at random',
            'No independent two-reviewer labels, external commit byte authentication or blinded test design',
            'Algorithmic QuixBugs GCD source is a prior semantic transcription, not authenticated upstream bytes',
            'No source code is executed; expected faulty/correct status is a curator claim',
            'Possible-unbound is a static observation, never a verified bug or causal explanation',
            'Wilson intervals describe only the curated observed subset and cannot justify population claims',
            'Unknown and out-of-scope samples are always reported outside decided confusion matrix',
        ],'verified_findings':[],'verified_root_causes':[]}
    return report


def replay_equivalent(root: Path | str, supplied:dict) -> bool:
    """Independently recompute all facts and all metrics from frozen source."""
    return supplied==evaluate_casebook(root)


def fingerprint_report(report:dict) -> str:
    return sha256(canonical(report))
