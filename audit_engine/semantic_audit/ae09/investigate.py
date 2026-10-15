"""AE-09: source-bound, conservative correlation of untrusted runtime logs.

A traceback is an observation, not proof of causality. Only static IMPORTS
relationships may be used to propose review candidates. No execution of log text.
"""
from __future__ import annotations

from collections import defaultdict, deque
import hashlib
import os
from pathlib import Path
import re
from typing import Any

from audit_engine.semantic_audit.ae01.publication import canonical, sha, _no_symlink_components
from audit_engine.semantic_audit.ae01.source import module_name
from audit_engine.semantic_audit.ae02.snapshots import load_generation
from audit_engine.semantic_audit.verification.immutable_payload import thaw
from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph, SemanticNode, SemanticEdge
from audit_engine.semantic_audit.graph.analysis.identity import graph_fingerprint
from audit_engine.semantic_audit.graph.analysis.engine import GraphAnalysisEngine
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType

MAX_LOG_BYTES = 2_000_000
MAX_EVENTS = 512
MAX_LOG_LINES = 50_000
FRAME = re.compile(r'^\s*File ["\'](?P<path>[^"\']{1,1024})["\'], line (?P<line>\d{1,9})(?:, in .*)?$')
PYTEST = re.compile(r'^\s*(?P<path>(?:[A-Za-z]:)?[^\s:]{1,1024}\.py):(?P<line>\d{1,9})(?::(?:in .*)?)?\s*$')
PYTEST_SUMMARY = re.compile(r'^\s*(?P<path>[^\s:]{1,1024}\.py):(?P<line>\d{1,9}):\s+(?P<kind>[A-Za-z_]\w*(?:Error|Exception|Failure|Warning))(?::|\b)')
GH_ANNOTATION = re.compile(r'^::error\s+file=(?P<path>[^,\r\n]{1,1024}),line=(?P<line>\d{1,9})(?:,|::)')
EXCEPTION = re.compile(r'^(?:[A-Za-z_]\w*\.)*(?:[A-Za-z_]\w*(?:Error|Exception|Failure)|AssertionError|KeyboardInterrupt|SystemExit)(?::|\s*$)')
ANSI = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
CI_TIMESTAMP = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z\s+')


def _ci_line(line: str) -> str:
    line = ANSI.sub('',line).strip('\r')
    line = CI_TIMESTAMP.sub('',line,count=1)
    if line.startswith('##[error]'):
        line=line[len('##[error]'):]
    return line


def _log_bytes(path: Path | str) -> bytes:
    path = Path(os.path.abspath(path))
    _no_symlink_components(path)
    if not path.is_file() or path.stat().st_size > MAX_LOG_BYTES:
        raise ValueError('Missing or oversized log (2 MB limit)')
    with path.open('rb') as stream:
        data = stream.read(MAX_LOG_BYTES + 1)
    if len(data) > MAX_LOG_BYTES or b'\x00' in data:
        raise ValueError('Oversized or binary runtime log')
    data.decode('utf-8', errors='strict')
    return data



def classify_signals(raw: bytes) -> tuple[list[dict], bool]:
    """Record exception *classes* only; exception text may contain credentials."""
    result=[]
    truncated=False
    for i,line in enumerate(raw.decode('utf-8').splitlines(),1):
        line=_ci_line(line)
        stripped=line.strip()
        # Python, unittest and pytest-style exception class notices.
        if stripped.startswith('E   '):
            stripped=stripped[4:].strip()
        if EXCEPTION.match(stripped):
            kind=stripped.split(':',1)[0].strip()
            if len(kind)<=120:
                if len(result)==MAX_EVENTS:
                    truncated=True
                    break
                result.append({'signal':'exception_class_observed','exception_class':kind,'log_line':i})
    return result,truncated

def _normalized(name: str) -> str | None:
    name = name.replace('\\', '/')
    if '\x00' in name or name.startswith('//') or re.match(r'^[A-Za-z]:[^/]',name):
        return None
    absolute = name.startswith('/') or bool(re.match(r'^[A-Za-z]:/',name))
    parts = name.split('/')
    # Absolute build-runner prefixes are untrusted. Relative traversals cannot be scoped.
    if '..' in parts:
        return None
    if not absolute and any(p in ('', '.') for p in parts[1:]):
        return None
    return '/'.join(p for p in parts if p not in ('', '.'))


def extract_events(raw: bytes) -> tuple[list[dict], list[str]]:
    """Produce line-indexed observations without storing log messages/secrets."""
    text = raw.decode('utf-8',errors='strict')
    lines = text.splitlines()
    issues = []
    if len(lines)>MAX_LOG_LINES:
        raise ValueError('Too many log lines')
    observations = []
    for i, original in enumerate(lines, 1):
        line = _ci_line(original)
        match, style = None, None
        for name, pattern in (('python_traceback',FRAME),('pytest_summary',PYTEST_SUMMARY),
                              ('github_annotation',GH_ANNOTATION),('pytest_frame',PYTEST)):
            match = pattern.match(line)
            if match:
                style=name
                break
        if match:
            if len(observations) >= MAX_EVENTS:
                issues.append('event_limit_exceeded')
                break
            row = {'kind':style,'log_line':i,'path':match.group('path'),
                   'source_line':int(match.group('line')),
                   'observation_id':sha(canonical([i,style,match.group('path'),match.group('line')]))[:24]}
            if row['source_line']<=0:
                issues.append('invalid_source_line')
            else:
                observations.append(row)
    if not observations:
        issues.append('no_parseable_source_frame')
    return observations,issues


def _match_path(path: str, files: dict) -> tuple[str, str | None, list[str]]:
    candidate=_normalized(path)
    if candidate is None:
        return 'unsafe',None,[]
    if candidate in files:
        return 'exact',candidate,[candidate]
    # Longest matching component suffix. Weak basenames are explicitly labeled.
    parts=candidate.split('/')
    ranks=[]
    for name in files:
        target=name.split('/')
        amount=0
        while amount<min(len(parts),len(target)) and parts[-1-amount]==target[-1-amount]:
            amount+=1
        if amount:
            ranks.append((amount,name))
    if not ranks:
        return 'unresolved',None,[]
    best=max(r for r,_ in ranks)
    winners=sorted(name for rank,name in ranks if rank==best)
    if len(winners)!=1:
        return 'ambiguous',None,winners
    return ('suffix' if best>=2 else 'weak_basename'),winners[0],winners


def _graph_inputs(generation) -> tuple[dict,SemanticGraph]:
    data=thaw(generation.policy_graph)
    graph=SemanticGraph(nodes=[SemanticNode(n['id'],n['type'],n['attributes'],n['metadata']) for n in data['nodes']],
                        edges=[SemanticEdge(e['source'],e['target'],e['relation'],e['attributes'],e['metadata']) for e in data['edges']])
    if graph_fingerprint(graph)!=generation.report['policy_graph_fingerprint']:
        raise ValueError('G3 policy graph fingerprint mismatch')
    reverse=defaultdict(list)
    for edge in graph.edges:
        if edge.relation_type=='IMPORTS':
            occurrence=edge.metadata.get('occurrence_id')
            source=edge.metadata.get('source_id')
            if not occurrence or not source:
                raise ValueError('Graph edge missing source occurrence evidence')
            reverse[edge.target_id].append((edge.source_id,occurrence,source))
    return reverse,graph


def build_report(ae01_output: Path | str, log_file: Path | str, source_root: Path | str, *,
                 generation_id: str | None = None, max_depth: int = 3,
                 max_candidates: int = 250) -> dict[str,Any]:
    if not 0<=max_depth<=20 or not 1<=max_candidates<=10000:
        raise ValueError('Invalid bounded dependency-analysis parameters')
    raw=_log_bytes(log_file)
    gen=load_generation(ae01_output,generation_id,source_root=Path(source_root))
    included={row['path']:row['sha256'] for row in gen.manifest['files'] if row['status']=='included'}
    observed, issues=extract_events(raw)
    signals,signal_limit=classify_signals(raw)
    if signal_limit:issues.append('signal_limit_exceeded')
    reverse,graph=_graph_inputs(gen)
    correlated=[]
    seeds=set()
    for event in observed:
        strategy,path,options=_match_path(event['path'],included)
        # Never persist raw paths: absolute traceback paths may disclose user information.
        row={k:v for k,v in event.items() if k!='path'}
        row['path_digest']=sha(event['path'].encode('utf-8'))
        row['match_strategy']=strategy
        row['candidate_paths']=options[:20]
        if len(options)>20:
            issues.append('ambiguous_match_budget_exceeded')
        if path:
            row['source_path']=path
            row['source_sha256']=included[path]
            row['module']=module_name(path)
            if strategy=='weak_basename':issues.append('weak_basename_path_match')
            # Traceback location is checked against actual snapshotted content when source_root supplied.
            source_path=Path(os.path.abspath(Path(source_root)/path))
            _no_symlink_components(source_path)
            blob=source_path.read_bytes()
            if sha(blob)!=included[path]:
                raise ValueError('Source bytes changed between generation verification and runtime correlation')
            source_lines=blob.splitlines(keepends=True)
            if event['source_line']>len(source_lines):
                row['match_strategy']='line_out_of_range'
                issues.append('source_line_out_of_range')
            else:
                row['source_line_sha256']=sha(source_lines[event['source_line']-1])
                if strategy in ('exact','suffix','weak_basename'):
                    seeds.add('module:'+row['module'])
        else:
            issues.append('unresolved_runtime_frame')
        correlated.append(row)
    candidate_map={}
    queue=deque((s,0,[]) for s in sorted(seeds))
    truncated=False
    while queue:
        node,depth,witness=queue.popleft()
        if node in candidate_map:
            continue
        if len(candidate_map)>=max_candidates:
            truncated=True
            break
        candidate_map[node]={'module':node.removeprefix('module:'),'depth':depth,
                             'import_occurrence_path':witness,'reason': 'observed_traceback_frame' if depth==0 else 'static_import_dependent'}
        parents=sorted(reverse.get(node, []))
        if parents and depth==max_depth:
            if any(src not in candidate_map for src,_,_ in parents):truncated=True
            continue
        for parent,occurrence,_ in parents:
            if parent not in candidate_map:
                queue.append((parent,depth+1,witness+[occurrence]))
    if truncated:issues.append('graph_traversal_budget_exceeded')
    # Run actual G3 dependency analysis on the source modules, not a parallel graph engine.
    analyses=[]
    analyzer=GraphAnalysisEngine(graph)
    for node in sorted(seeds):
        if graph.get_node(node) is None:
            issues.append('runtime_module_not_in_policy_graph')
            continue
        result=analyzer.execute(GraphQuery('ae09:'+node,QueryType.DEPENDENCY,[node],
                             {'max_depth':1,'relation_types':['IMPORTS']}))
        analyses.append({'module':node.removeprefix('module:'),'analysis_id':result.analysis_id,
                         'graph_fingerprint':result.graph_fingerprint,
                         'observation_count':len(result.observations)})
    if gen.report['assurance_completeness']!='complete_within_declared_scope':
        issues.append('underlying_source_audit_inconclusive')
    # Deduplicated fixed vocabulary; independent replay recomputes all results.
    issues=sorted(set(issues))
    data={'schema':'ae09/runtime_investigation/v1',
          'ae01_generation':gen.snapshot.generation_id,
          'ae01_seal_sha256':gen.snapshot.publication_seal_hash,
          'source_digest':gen.snapshot.source_digest,
          'policy_graph_fingerprint':gen.report['policy_graph_fingerprint'],
          'log_sha256':sha(raw), 'log_bytes':len(raw),
          'bounds':{'max_depth':max_depth,'max_candidates':max_candidates,'max_log_bytes':MAX_LOG_BYTES},
          'observations':correlated,
          'failure_signals':signals,
          'graph_analyses':analyses,
          'review_candidates':sorted(candidate_map.values(),key=lambda x:(x['depth'],x['module'])),
          'issues':issues,
          'assurance_status':'bounded_correlation' if correlated and not issues else 'inconclusive',
          'conclusion':'review_hypotheses_only_not_proven_root_cause'}
    data['record_sha256']=sha(canonical(data))
    return data


def verify_report(record:dict,ae01_output:Path|str,log_file:Path|str,source_root:Path|str) -> dict:
    if not isinstance(record,dict) or not isinstance(record.get('bounds'),dict):
        raise ValueError('Invalid investigation record')
    b=record['bounds']
    replay=build_report(ae01_output,log_file,source_root,generation_id=record.get('ae01_generation'),
                        max_depth=b['max_depth'],max_candidates=b['max_candidates'])
    if canonical(replay)!=canonical(record):
        raise ValueError('Runtime investigation differs from independently replayed evidence')
    return {'verified':True,'observations':len(replay['observations']),
            'review_candidates':len(replay['review_candidates']),
            'assurance_status':replay['assurance_status']}
