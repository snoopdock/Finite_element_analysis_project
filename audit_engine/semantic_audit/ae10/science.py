"""AE-10: bounded scientific claim/evidence and numerical consistency audit.

Graph support is a declared relation, not proof of claim truth. Numeric checks compare
specified fields in immutable local artifacts using exact base-10 arithmetic.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any

from audit_engine.semantic_audit.ae01.publication import canonical, sha, _no_symlink_components
from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph, SemanticNode, SemanticEdge
from audit_engine.semantic_audit.graph.analysis.identity import graph_fingerprint
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.rules import DomainRuleExecutor, DomainRuleLoader
from audit_engine.semantic_audit.verification import (VerifierRegistry, RequiredRelationshipVerifier,
                                                      VerificationService)

SCHEMA = 'ae10/scientific-audit/v1'
SPEC = 'ae10/scientific-spec/v1'
MAX_SPEC = 200_000
MAX_ARTIFACT = 2_000_000
MAX_CLAIMS = 250
MAX_ARTIFACTS = 250
MAX_CHECKS = 1000
IDENT = re.compile(r'^[a-zA-Z][a-zA-Z0-9_.-]{0,79}$')
SHA = re.compile(r'^[0-9a-f]{64}$')


def _reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON member')
        result[key] = value
    return result


def _json(data: bytes) -> Any:
    return json.loads(data.decode('utf-8', 'strict'), object_pairs_hook=_reject_duplicates,
                      parse_float=Decimal, parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON constant')))


def _plain_json(data: bytes) -> Any:
    # For source specification only: users must encode quantities as decimal strings.
    return json.loads(data.decode('utf-8', 'strict'), object_pairs_hook=_reject_duplicates,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON constant')))


def _real(root: Path | str) -> Path:
    p = Path(os.path.abspath(root))
    _no_symlink_components(p)
    return p


def _relative(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 300 or '\\' in value or '\x00' in value:
        raise ValueError('Invalid artifact path')
    parts = value.split('/')
    if value.startswith('/') or any(not p or p in ('.', '..') for p in parts) or any(':' in p for p in parts):
        raise ValueError('Unsafe artifact path')
    return value


def _artifact(root: Path, rel: str) -> bytes:
    rel = _relative(rel)
    p = root / rel
    _no_symlink_components(p)
    if not p.is_file() or p.stat().st_size > MAX_ARTIFACT:
        raise ValueError('Artifact missing, not regular, or oversized')
    data = p.read_bytes()
    if len(data) > MAX_ARTIFACT:
        raise ValueError('Artifact changed or too large')
    return data


def _dec(value: Any) -> Decimal:
    # Fail closed rather than silently converting IEEE binary floats.
    if not isinstance(value, (str, int, Decimal)) or isinstance(value, bool):
        raise ValueError('Quantity must be decimal string or integer')
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError('Invalid decimal quantity') from exc
    if not result.is_finite() or len(result.as_tuple().digits) > 80 or abs(result.as_tuple().exponent) > 40:
        raise ValueError('Unbounded decimal quantity')
    return result


def _pointer(data: Any, pointer: str) -> Any:
    if not isinstance(pointer, str) or not pointer.startswith('/') or len(pointer) > 300:
        raise ValueError('Invalid JSON pointer')
    current = data
    for token in pointer.split('/')[1:]:
        if re.search(r'~(?![01])', token):
            raise ValueError('Invalid JSON pointer escape')
        token = token.replace('~1', '/').replace('~0', '~')
        if isinstance(current, dict):
            if token not in current:
                raise KeyError('Measurement pointer missing')
            current = current[token]
        elif isinstance(current, list):
            if not re.fullmatch(r'0|[1-9][0-9]*', token) or int(token) >= len(current):
                raise KeyError('Measurement index missing')
            current = current[int(token)]
        else:
            raise KeyError('Measurement pointer not traversable')
    return current


def _validate_spec(spec: Any) -> None:
    if not isinstance(spec, dict) or set(spec) != {'schema', 'artifacts', 'claims'} or spec['schema'] != SPEC:
        raise ValueError('Invalid AE-10 specification schema')
    artifacts, claims = spec['artifacts'], spec['claims']
    if not isinstance(artifacts, list) or not (1 <= len(artifacts) <= MAX_ARTIFACTS):
        raise ValueError('Empty or oversized artifact scope')
    if not isinstance(claims, list) or not (1 <= len(claims) <= MAX_CLAIMS):
        raise ValueError('Empty or oversized claim scope')
    aids = set()
    for a in artifacts:
        if not isinstance(a, dict) or set(a) != {'id', 'path', 'sha256'}:
            raise ValueError('Invalid artifact definition')
        if not isinstance(a['id'], str) or not IDENT.fullmatch(a['id']) or a['id'] in aids:
            raise ValueError('Duplicate/invalid evidence ID')
        aids.add(a['id'])
        _relative(a['path'])
        if not isinstance(a['sha256'], str) or not SHA.fullmatch(a['sha256']):
            raise ValueError('Invalid declared source digest')
    cids, all_checks = set(), set()
    for c in claims:
        if not isinstance(c, dict) or set(c) != {'id', 'statement_sha256', 'statement_path', 'supports', 'checks'}:
            raise ValueError('Invalid claim definition')
        if not isinstance(c['id'], str) or not IDENT.fullmatch(c['id']) or c['id'] in cids:
            raise ValueError('Duplicate/invalid claim ID')
        cids.add(c['id'])
        if not isinstance(c['statement_sha256'], str) or not SHA.fullmatch(c['statement_sha256']):
            raise ValueError('Claim statement digest missing')
        _relative(c['statement_path'])
        if not isinstance(c['supports'], list) or any(s not in aids for s in c['supports']) or len(set(c['supports'])) != len(c['supports']):
            raise ValueError('Unknown or repeated support target')
        if not isinstance(c['checks'], list) or len(c['checks']) > MAX_CHECKS:
            raise ValueError('Invalid numerical check list')
        for k in c['checks']:
            required = {'id','artifact','pointer','unit','op','expected','tolerance'}
            if not isinstance(k, dict) or set(k) != required or not isinstance(k['id'], str) or not IDENT.fullmatch(k['id']):
                raise ValueError('Invalid numerical check schema')
            if k['id'] in all_checks:
                raise ValueError('Duplicate global numerical check ID')
            all_checks.add(k['id'])
            if k['artifact'] not in c['supports'] or k['op'] not in ('eq','ge','le','between'):
                raise ValueError('Check target or operation not supported')
            if not isinstance(k['unit'], str) or not 0 < len(k['unit']) <= 40 or not isinstance(k['pointer'], str):
                raise ValueError('Invalid unit or pointer')
            if k['op'] == 'between':
                if not isinstance(k['expected'], list) or len(k['expected']) != 2 or _dec(k['expected'][0]) > _dec(k['expected'][1]):
                    raise ValueError('Invalid interval')
            else:
                _dec(k['expected'])
            if _dec(k['tolerance']) < 0:
                raise ValueError('Negative tolerance')
    if len(all_checks) > MAX_CHECKS:
        raise ValueError('Numerical check budget exceeded')


def _evaluate(k: dict, data: Any) -> dict:
    try:
        record = _pointer(data, k['pointer'])
        if not isinstance(record, dict) or set(record) != {'value', 'unit'}:
            raise ValueError('Measurement must contain only value and unit')
        if record['unit'] != k['unit']:
            raise ValueError('Unit disagreement; implicit conversions forbidden')
        observed = _dec(record['value'])
        tolerance = _dec(k['tolerance'])
        # Up to 80 mantissa digits and exponent magnitude 40 are admitted.
        # Decimal's default context (28 digits) is NOT sufficient for a
        # scientific comparison of two large, nearly identical quantities.
        with localcontext() as context:
            context.prec = 200
            if k['op'] == 'between':
                low, high = map(_dec, k['expected'])
                success = low - tolerance <= observed <= high + tolerance
            else:
                expected = _dec(k['expected'])
                success = {'eq': lambda: abs(observed-expected) <= tolerance,
                           'ge': lambda: observed + tolerance >= expected,
                           'le': lambda: observed - tolerance <= expected}[k['op']]()
        return {'id':k['id'], 'status':'consistent' if success else 'inconsistent',
                'observed': str(observed), 'pointer':k['pointer'], 'unit': k['unit']}
    except (KeyError, ValueError, TypeError, InvalidOperation) as exc:
        return {'id':k['id'], 'status':'unassessed', 'reason':type(exc).__name__,
                'pointer':k['pointer'], 'unit':k['unit']}


def build_report(spec_file:Path|str, artifacts_root:Path|str) -> dict:
    spec_path = _real(spec_file)
    root = _real(artifacts_root)
    if not root.is_dir() or not spec_path.is_file() or spec_path.stat().st_size > MAX_SPEC:
        raise ValueError('Missing or oversized scientific audit specification')
    source_spec = spec_path.read_bytes()
    if len(source_spec) > MAX_SPEC:
        raise ValueError('Scientific specification changed during read')
    spec = _plain_json(source_spec)
    _validate_spec(spec)
    graph = SemanticGraph()
    loaded = {}
    scope = []
    for a in sorted(spec['artifacts'], key=lambda x:x['id']):
        row={'id':a['id'],'path':a['path'],'declared_sha256':a['sha256']}
        try:
            raw=_artifact(root,a['path'])
            row['observed_sha256']=sha(raw)
            if row['observed_sha256'] != a['sha256']:
                row['status']='hash_mismatch'
            else:
                loaded[a['id']]=_json(raw)
                row['status']='available'
        except (OSError,ValueError,UnicodeError,TypeError) as exc:
            row['status']='unavailable'
            row['reason']=type(exc).__name__
        scope.append(row)
        graph.add_node(SemanticNode('evidence:'+a['id'],'EvidenceArtifact',
                                     {'source_sha256':a['sha256'],'path':a['path'],'status':row['status']}))
    index={r['id']:r for r in scope}
    claims=[]
    for claim in sorted(spec['claims'],key=lambda x:x['id']):
        try:
            statement_bytes = _artifact(root, claim['statement_path'])
            statement_status = 'available' if sha(statement_bytes) == claim['statement_sha256'] else 'hash_mismatch'
        except (OSError, ValueError) :
            statement_status = 'unavailable'
        graph.add_node(SemanticNode('claim:'+claim['id'],'ScientificClaim',
                                    {'statement_sha256':claim['statement_sha256'],
                                     'statement_path':claim['statement_path'],
                                     'statement_status':statement_status}))
        for aid in sorted(claim['supports']):
            graph.add_edge(SemanticEdge('claim:'+claim['id'], 'evidence:'+aid, 'SUPPORTED_BY',
                                       metadata={'source_id':aid,'source_sha256':index[aid]['declared_sha256']}))
        checks=[]
        for k in sorted(claim['checks'], key=lambda x:x['id']):
            result=_evaluate(k,loaded[k['artifact']]) if k['artifact'] in loaded else {
                'id':k['id'],'status':'unassessed','reason':'source_unavailable',
                'pointer':k['pointer'],'unit':k['unit']}
            result['artifact']=k['artifact']
            result['source_sha256']=index[k['artifact']]['declared_sha256']
            checks.append(result)
        claims.append({'id':claim['id'],'statement_sha256':claim['statement_sha256'],
                       'statement_path':claim['statement_path'],'statement_status':statement_status,
                       'supports':sorted(claim['supports']), 'checks':checks})
    # Reuse G3's real scientific support rule and verification receipts. Its finding
    # establishes a graph-scoped missing *relationship*, not scientific falsehood.
    policy_path=Path(__file__).resolve().parents[3]/'specs/rules/scientific/claim_requires_support_relationship.yaml'
    policy_bytes=policy_path.read_bytes()
    rule=DomainRuleLoader.from_yaml(policy_path)
    registry=VerifierRegistry()
    registry.register(RequiredRelationshipVerifier())
    executor=DomainRuleExecutor(VerificationService(registry))
    graph_checks=[]
    for c in claims:
        result=SemanticGraphAnalysisService(graph).analyze(GraphQuery('ae10:'+c['id'],QueryType.STRUCTURAL,
            ['claim:'+c['id']],{'direction':'outgoing','relation_types':['SUPPORTED_BY']}))
        exe=executor.execute(rule,result,graph)
        graph_checks.append({'claim_id':c['id'],'execution':exe.to_dict()})
    if len(graph_checks) != len(claims) or any(g['execution']['reason']!='executed' or
        len(g['execution']['obligations'])!=1 or len(g['execution']['receipts'])!=1 or
        g['execution']['receipts'][0]['evidence_state']!='validated' or
        g['execution']['receipts'][0]['decision'] in ('inconclusive','error') for g in graph_checks):
        raise ValueError('G3 scientific support rule execution incomplete')
    has_missing=any(not c['supports'] for c in claims)
    mismatched=any(check['status']=='inconsistent' for c in claims for check in c['checks'])
    incomplete=any(r['status']!='available' for r in scope) or any(not c['checks'] or
         any(x['status']=='unassessed' for x in c['checks']) for c in claims) or has_missing or any(c['statement_status']!='available' for c in claims)
    # Assurance claims strictly bounded: structural support and declared quantitative consistency.
    verdict='inconclusive' if incomplete else 'inconsistent' if mismatched else 'consistent_within_declared_checks'
    body={'schema':SCHEMA,'spec_sha256':sha(source_spec),'rule_sha256':sha(policy_bytes),
          'graph':graph.to_dict(),'graph_fingerprint':graph_fingerprint(graph),
          'artifacts':scope,'claims':claims,'g3_scientific_support_executions':graph_checks,
          'verdict':verdict,'limitations':['declared relationships do not establish causal or scientific validity',
          'no implicit unit conversion, no external literature verification',
          'accuracy limited to named JSON fields and declared numerical checks']}
    body['record_sha256']=sha(canonical(body))
    return body


def verify_report(report:dict, spec_file:Path|str, artifacts_root:Path|str) -> dict:
    if not isinstance(report,dict) or not isinstance(report.get('record_sha256'),str):
        raise ValueError('AE-10 report format invalid')
    body={k:v for k,v in report.items() if k!='record_sha256'}
    if sha(canonical(body)) != report['record_sha256']:
        raise ValueError('AE-10 report checksum mismatch')
    fresh=build_report(spec_file,artifacts_root)
    if canonical(fresh)!=canonical(report):
        raise ValueError('Source, policy, graph or scientific evidence disagrees')
    return {'record_sha256':report['record_sha256'],'verdict':report['verdict'],
            'verified_claims':len(report['claims']),'verified_artifacts':len(report['artifacts'])}
