"""AE-16: bounded, declarative operational evidence ledger on the canonical graph.

This checks consistency of supplied execution records and supporting bytes; it
DOES NOT authenticate GitHub's job status or assert that a command ran. Data is
never executed. A step's claimed success is not a verified execution fact.
"""
from __future__ import annotations

import json
import os
import re
import stat
from collections import defaultdict
from pathlib import Path
from typing import Any

from audit_engine.semantic_audit.ae01.publication import canonical, sha, _no_symlink_components
from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph, SemanticNode, SemanticEdge
from audit_engine.semantic_audit.graph.analysis.identity import graph_fingerprint

SCHEMA = 'ae16/declared_execution/v1'
REPORT_SCHEMA = 'ae16/operational_observation/v1'
MAX_DECLARATION = 1_000_000
MAX_SINGLE_EVIDENCE = 2_000_000
MAX_TOTAL_EVIDENCE = 24_000_000
MAX_JOBS = 32
MAX_STEPS = 128
MAX_CHECKS = 512
MAX_REQUIREMENTS = 256
MAX_ARTIFACTS = 512
IDENT = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$')
STATUSES = frozenset({'success', 'failure', 'skipped', 'cancelled', 'unknown'})
CHECK_STATES = frozenset({'passed', 'failed', 'skipped', 'unknown'})
TEST_STATES = frozenset({'passed', 'failed', 'skipped'})


def _shape(item: Any, keys: set[str], required: set[str], kind: str) -> None:
    if not isinstance(item, dict) or not required.issubset(item) or set(item)-keys:
        raise ValueError(f'Invalid {kind} schema or unsupported keys')


def _id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not IDENT.fullmatch(value):
        raise ValueError(f'Invalid {label} identifier')
    return value


def _path(root: Path, name: Any) -> Path:
    if (not isinstance(name, str) or not name or len(name)>400 or '\\' in name or
        name.startswith('/') or ':' in name or any(s in ('', '.', '..') for s in name.split('/'))):
        raise ValueError('Unsafe evidence-relative path')
    result=root.joinpath(*name.split('/'))
    _no_symlink_components(result)
    return result


def _file(root: Path, name: Any, limit: int=MAX_SINGLE_EVIDENCE) -> bytes:
    p=_path(root,name)
    info=p.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size>limit:
        raise ValueError('Missing, nonregular, or oversized evidence file')
    with p.open('rb') as handle:
        blob=handle.read(limit+1)
    if len(blob)>limit:
        raise ValueError('Evidence exceeds byte budget')
    if p.stat().st_size!=len(blob):
        raise ValueError('Evidence changed while reading')
    return blob


def _read_declaration(path: Path) -> tuple[dict,bytes]:
    p=Path(os.path.abspath(path))
    _no_symlink_components(p)
    info=p.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size>MAX_DECLARATION:
        raise ValueError('Invalid declaration file')
    data=p.read_bytes()
    if len(data)>MAX_DECLARATION or b'\x00' in data:
        raise ValueError('Invalid declaration bytes')
    def no_duplicate_keys(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('Duplicate JSON property is not allowed')
            result[key]=value
        return result
    parsed=json.loads(data,object_pairs_hook=no_duplicate_keys)
    if not isinstance(parsed,dict) or canonical(parsed)!=data:
        raise ValueError('Declaration must be canonical JSON with a single object')
    return parsed,data


def _graph_doc(graph:SemanticGraph) -> dict:
    return {'nodes':[{'id':n.node_id,'type':n.entity_type,'attributes':n.attributes,'metadata':n.metadata} for n in graph.nodes],
            'edges':[{'source':e.source_id,'target':e.target_id,'relation':e.relation_type,
                      'attributes':e.attributes,'metadata':e.metadata} for e in graph.edges]}


def build_report(declaration_file: Path | str,evidence_root:Path | str,*,
                 ae01_output:Path | str | None=None,source_root:Path | str | None=None,
                 max_ae09_candidates:int=100) -> tuple[dict,dict]:
    """Replayable observations and graph; no code execution or verified findings."""
    evidence_root=Path(os.path.abspath(evidence_root))
    _no_symlink_components(evidence_root)
    if not evidence_root.is_dir(): raise ValueError('Evidence root must be a directory')
    if (ae01_output is None)!=(source_root is None):
        raise ValueError('AE-09 source correlation requires both AE-01 output and source root')
    if not 1<=max_ae09_candidates<=500:raise ValueError('Invalid correlation budget')
    document,raw=_read_declaration(Path(declaration_file))
    _shape(document,{'schema','run_id','reported_status','jobs','requirements'},
           {'schema','run_id','reported_status','jobs','requirements'},'run')
    if document['schema']!=SCHEMA:raise ValueError('Unsupported declaration schema')
    run_id=_id(document['run_id'],'run')
    if document['reported_status'] not in STATUSES:raise ValueError('Unknown declared run status')
    jobs=document['jobs']; requirements=document['requirements']
    if not isinstance(jobs,list) or not 1<=len(jobs)<=MAX_JOBS:raise ValueError('Invalid job count')
    if not isinstance(requirements,list) or len(requirements)>MAX_REQUIREMENTS:raise ValueError('Invalid requirement count')
    job_ids=set(); job_index={}; steps_by_key={}; checks_by_key={}; issues=[]
    graph=SemanticGraph()
    run_node='run:'+run_id
    graph.add_node(SemanticNode(run_node,'DeclaredExecution',{'reported_status':document['reported_status']},
                                {'source':'supplied_untrusted_declaration'}))
    def node(nid,typ,attrs=None):
        graph.add_node(SemanticNode(nid,typ,attrs or {},{'evidence_authority':'supplied_declaration'}))
    def edge(a,b,rel,attrs=None):
        graph.add_edge(SemanticEdge(a,b,rel,attrs or {},{'evidence_authority':'declared_relation'}))
    def issue(kind,where):issues.append({'kind':kind,'subject':where})
    total_steps=0;total_checks=0; total_artifacts=0
    files={}; total_bytes=0
    def evidence(name,kind):
        nonlocal total_bytes
        if name not in files:
            try:
                blob=_file(evidence_root,name)
            except FileNotFoundError:
                files[name]={'sha256':None,'size':None,'kind':kind,'state':'missing'}
                issue('missing_evidence_file',name)
            else:
                if kind=='log':
                    if b'\x00' in blob:raise ValueError('Binary step log evidence rejected')
                    try:blob.decode('utf-8',errors='strict')
                    except UnicodeDecodeError as exc:raise ValueError('Non-UTF-8 step log rejected') from exc
                total_bytes+=len(blob)
                if total_bytes>MAX_TOTAL_EVIDENCE:raise ValueError('Total evidence byte budget exceeded')
                files[name]={'sha256':sha(blob),'size':len(blob),'kind':kind,'state':'supplied'}
        elif files[name]['kind']!=kind:
            raise ValueError('Evidence path reused for incompatible roles')
        return files[name]
    for job in jobs:
        _shape(job,{'id','status','needs','steps'}, {'id','status','needs','steps'},'job')
        jid=_id(job['id'],'job')
        if jid in job_ids:raise ValueError('Duplicate job ID')
        job_ids.add(jid);job_index[jid]=job
        if job['status'] not in STATUSES:raise ValueError('Unknown job status')
        if not isinstance(job['needs'],list) or len(job['needs'])>MAX_JOBS or len(set(job['needs']))!=len(job['needs']):
            raise ValueError('Invalid job needs')
        if not isinstance(job['steps'],list) or not 1<=len(job['steps'])<=MAX_STEPS:
            raise ValueError('Invalid job steps')
        jnode='job:'+jid;node(jnode,'DeclaredJob',{'status':job['status']});edge(run_node,jnode,'HAS_JOB')
        seen_steps=set()
        for step in job['steps']:
            total_steps+=1
            if total_steps>MAX_STEPS:raise ValueError('Step budget exceeded')
            _shape(step,{'id','status','exit_code','log','checks','produces','consumes'},
                   {'id','status','exit_code','log','checks','produces','consumes'},'step')
            sid=_id(step['id'],'step')
            if sid in seen_steps:raise ValueError('Duplicate step ID')
            seen_steps.add(sid);steps_by_key[(jid,sid)]=step
            if step['status'] not in STATUSES:raise ValueError('Invalid step status')
            code=step['exit_code']
            if code is not None and (type(code) is not int or not -255<=code<=255):
                raise ValueError('Invalid exit code')
            snode=f'step:{jid}:{sid}'
            node(snode,'DeclaredStep',{'status':step['status'],'exit_code':code});edge(jnode,snode,'HAS_STEP')
            if step['status']=='success' and code!=0:issue('claimed_success_without_zero_exit',snode)
            if step['status']=='failure' and (code is None or code==0):issue('claimed_failure_without_nonzero_exit',snode)
            if step['status']=='skipped' and code is not None:issue('skipped_step_has_exit_code',snode)
            log=step['log']
            if log is not None:
                item=evidence(log,'log')
                ln='log:'+sha(log.encode())[:24]
                if graph.get_node(ln) is None:node(ln,'DeclaredLog',{'path':log,'sha256':item['sha256']})
                edge(snode,ln,'HAS_LOG_EVIDENCE' if item['sha256'] is not None else 'EXPECTS_LOG')
            if step['status'] in ('success','failure') and log is None:issue('executed_step_missing_log',snode)
            if step['status']=='skipped' and log is not None:issue('skipped_step_has_log',snode)
            checks=step['checks']
            if not isinstance(checks,list):raise ValueError('Invalid check list')
            seen_checks=set()
            for check in checks:
                total_checks+=1
                if total_checks>MAX_CHECKS:raise ValueError('Check budget exceeded')
                _shape(check,{'id','status','tests'},{'id','status','tests'},'check')
                cid=_id(check['id'],'check')
                if cid in seen_checks:raise ValueError('Duplicate check ID')
                seen_checks.add(cid);checks_by_key[(jid,sid,cid)]=(check,step)
                if check['status'] not in CHECK_STATES or not isinstance(check['tests'],list) or len(check['tests'])>100:
                    raise ValueError('Invalid check outcome or test count')
                cnode=f'check:{jid}:{sid}:{cid}'
                node(cnode,'DeclaredCheck',{'status':check['status']});edge(snode,cnode,'DECLARES_CHECK')
                if check['status']=='passed' and (step['status']!='success' or log is None or files[log]['sha256'] is None):
                    issue('passed_check_without_successful_evidenced_step',cnode)
                if check['status']=='passed' and not check['tests']:
                    issue('passed_check_without_test_oracle',cnode)
                seen_tests=set()
                for test in check['tests']:
                    _shape(test,{'id','expected','observed'}, {'id','expected','observed'},'nested_test')
                    tid=_id(test['id'],'nested test')
                    if tid in seen_tests:raise ValueError('Duplicate nested test ID')
                    seen_tests.add(tid)
                    if test['expected'] not in TEST_STATES or test['observed'] not in TEST_STATES:
                        raise ValueError('Invalid nested test result')
                    tnode=f'test:{jid}:{sid}:{cid}:{tid}'
                    node(tnode,'DeclaredNestedTest',{'expected':test['expected'],'observed':test['observed']})
                    edge(cnode,tnode,'HAS_NESTED_TEST')
                    if test['expected']!=test['observed']:
                        issue('nested_test_outcome_mismatch',tnode)
                if check['tests'] and check['status']=='passed' and any(t['expected']!=t['observed'] for t in check['tests']):
                    issue('passed_check_contains_failed_oracle',cnode)
            for key in ('produces','consumes'):
                if not isinstance(step[key],list):raise ValueError('Invalid artifact list')
                total_artifacts+=len(step[key])
                if total_artifacts>MAX_ARTIFACTS:raise ValueError('Artifact budget exceeded')
    for j,record in job_index.items():
        for dep in record['needs']:
            if not isinstance(dep,str) or dep not in job_ids or dep==j:raise ValueError('Unknown or self job dependency')
            edge('job:'+j,'job:'+dep,'NEEDS_JOB')
    visiting=set();visited=set()
    def visit(job):
        if job in visiting:raise ValueError('Cyclic job dependencies')
        if job in visited:return
        visiting.add(job)
        for parent in job_index[job]['needs']:visit(parent)
        visiting.remove(job);visited.add(job)
    for j in sorted(job_ids):visit(j)
    def predecessors(job):
        result=set();pending=list(job_index[job]['needs'])
        while pending:
            name=pending.pop()
            if name not in result:
                result.add(name);pending.extend(job_index[name]['needs'])
        return result
    producers={}
    for jid,job in job_index.items():
        for pos,step in enumerate(job['steps']):
            for item in step['produces']:
                _shape(item,{'id','path'},{'id','path'},'produced artifact')
                aid=_id(item['id'],'artifact')
                if aid in producers:raise ValueError('Duplicate artifact ID across producers')
                record=evidence(item['path'],'artifact')
                producers[aid]={'job':jid,'step':step['id'],'index':pos,'path':item['path'],
                                'sha256':record['sha256'],'status':step['status']}
                anode='artifact:'+aid
                node(anode,'DeclaredArtifact',{'digest':record['sha256']})
                edge(f'step:{jid}:{step["id"]}',anode,
                     'PRODUCES' if record['sha256'] is not None else 'DECLARES_PRODUCTION',
                     {'file_sha256':record['sha256']})
                if step['status']!='success':issue('artifact_from_non_successful_producer',anode)
    for jid,job in job_index.items():
        for pos,step in enumerate(job['steps']):
            for item in step['consumes']:
                _shape(item,{'id','path'},{'id','path'},'consumed artifact')
                aid=_id(item['id'],'artifact')
                target=evidence(item['path'],'artifact')
                if aid not in producers:
                    issue('consumer_without_declared_producer',f'step:{jid}:{step["id"]}')
                    continue
                producer=producers[aid]
                edge(f'step:{jid}:{step["id"]}','artifact:'+aid,
                     'CONSUMES' if target['sha256'] is not None else 'DECLARES_CONSUMPTION',
                     {'file_sha256':target['sha256'],'path_digest':sha(item['path'].encode())})
                if target['sha256']!=producer['sha256']:
                    issue('producer_consumer_content_mismatch',f'step:{jid}:{step["id"]}')
                if producer['job']==jid:
                    if producer['index']>=pos:issue('artifact_consumed_before_production',f'step:{jid}:{step["id"]}')
                elif producer['job'] not in predecessors(jid):
                    issue('missing_producer_job_dependency',f'job:{jid}')
                if producer['status']!='success' or step['status']!='success':
                    issue('artifact_transfer_without_successful_steps',f'step:{jid}:{step["id"]}')
    required_ids=set();coverage=[]
    for required in requirements:
        _shape(required,{'id','job','step','check'}, {'id','job','step','check'},'requirement')
        rid=_id(required['id'],'requirement')
        if rid in required_ids:raise ValueError('Duplicate requirement ID')
        required_ids.add(rid)
        key=tuple(_id(required[field],field) for field in ('job','step','check'))
        rnode='requirement:'+rid
        node(rnode,'DeclaredRequiredCheck',{'target':list(key)})
        edge(run_node,rnode,'REQUIRES_CHECK')
        if key not in checks_by_key:
            coverage.append({'id':rid,'state':'missing','target':list(key)})
            issue('required_check_not_executed',rnode)
            continue
        check,step=checks_by_key[key]
        edge(rnode, f'check:{key[0]}:{key[1]}:{key[2]}','TARGETS_CHECK')
        state='observed_pass_claim' if (check['status']=='passed' and step['status']=='success' and step['log'] is not None and files[step['log']]['sha256'] is not None and
                                        bool(check['tests']) and all(t['expected']==t['observed'] for t in check['tests'])) else 'incomplete_or_failed'
        coverage.append({'id':rid,'state':state,'target':list(key)})
        if state!='observed_pass_claim':issue('required_check_not_satisfied',rnode)
    if not requirements:issue('no_required_check_contract',run_node)
    if document['reported_status']=='success' and any(j['status'] not in ('success','skipped') for j in jobs):
        issue('declared_run_status_inconsistent_with_jobs',run_node)
    for job in jobs:
        if job['status']=='success' and any(s['status']=='failure' for s in job['steps']):
            issue('claimed_job_success_contains_failed_step','job:'+job['id'])
        if job['status']=='success' and any(j['status']!='success' for j in (job_index[d] for d in job['needs'])):
            issue('job_success_with_unsuccessful_dependency','job:'+job['id'])
    correlations=[]
    if ae01_output is not None:
        from audit_engine.semantic_audit.ae09.investigate import build_report as ae09_build
        for jid,job in job_index.items():
            for step in job['steps']:
                if step['log'] is not None and files[step['log']]['sha256'] is not None:
                    result=ae09_build(ae01_output,_path(evidence_root,step['log']),source_root,
                                      max_candidates=max_ae09_candidates)
                    correlations.append({'job':jid,'step':step['id'],'log_sha256':result['log_sha256'],
                                         'ae01_generation':result['ae01_generation'],
                                         'frames':len(result['observations']),
                                         'failure_signals':len(result['failure_signals']),
                                         'assurance_status':result['assurance_status'],
                                         'issues':result['issues'],
                                         'conclusion':result['conclusion']})
    issues=sorted({(v['kind'],v['subject']) for v in issues})
    graph_doc=_graph_doc(graph)
    outcome={'schema':REPORT_SCHEMA,'run_id':run_id,'declaration_sha256':sha(raw),
             'reported_status':document['reported_status'],
             'source_authority':'untrusted_execution_declaration_not_github_authenticated',
             'evidence_authority':'exact_supplied_bytes_not_proof_of_execution',
             'verification_authority':'source_replay_only_not_runtime_or_causal_proof',
             'assurance':'incomplete_or_inconsistent' if issues else 'consistent_declared_observations_unattested',
             'verified_findings':[],
             'required_check_coverage':coverage,
             'coverage_summary':{'required':len(requirements),
                  'observed_pass_claims':sum(r['state']=='observed_pass_claim' for r in coverage)},
             'issues':[{'kind':a,'subject':b} for a,b in issues],
             'files':{k:files[k] for k in sorted(files)},
             'source_correlations':correlations,
             'graph_fingerprint':graph_fingerprint(graph),
             'bounds':{'max_ae09_candidates':max_ae09_candidates}}
    return outcome,graph_doc
