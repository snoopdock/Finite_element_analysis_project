"""AE-12 bounded, source-bound Python *failure-mode observations*.

This is not a whole-program proof or a scanner for arbitrary Python semantics.
All conclusions are replayed from exact source bytes in a verified AE-01 generation.
"""
from __future__ import annotations

import ast
from collections import defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from audit_engine.semantic_audit.ae01.publication import canonical, sha, _no_symlink_components
from audit_engine.semantic_audit.ae01.source import module_name
from audit_engine.semantic_audit.ae02.snapshots import load_generation
from audit_engine.semantic_audit.ae09.investigate import build_report as correlate_runtime, _graph_inputs
from audit_engine.semantic_audit.graph.analysis.engine import GraphAnalysisEngine
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType

SCHEMA = 'ae12/code_failure_modes/v1'
RULES = frozenset({'mutable_default', 'swallowed_exception', 'bare_except',
                   'finally_return', 'duplicate_dict_key', 'assert_call', 'subprocess_shell'})
MAX_SOURCE_FILES = 2500
MAX_FINDINGS = 2000
MAX_GRAPH_MODULES = 24


def load_policy(policy_path: Path | str) -> tuple[dict, str]:
    p = Path(policy_path).absolute()
    _no_symlink_components(p)
    data = p.read_bytes()
    policy = json.loads(data)
    if not isinstance(policy, dict) or set(policy) != {'schema', 'paths', 'rules', 'max_findings', 'max_graph_modules'}:
        raise ValueError('Policy schema and fields must be explicit')
    if policy['schema'] != 'ae12/policy/v1' or not isinstance(policy['paths'], list) or not policy['paths']:
        raise ValueError('Invalid policy version or empty source scope')
    paths = policy['paths']
    if not all(isinstance(p,str) and p and (p == '*' or (not p.startswith('/') and
                 not any(x in ('.', '..', '') for x in p.split('/')) and p.endswith('.py'))) for p in paths):
        raise ValueError('Policy paths must be repository-relative Python file names or *')
    if '*' in paths and paths != ['*'] or len(paths) != len(set(paths)):
        raise ValueError('Ambiguous source selection')
    rules = policy['rules']
    if (not isinstance(rules, list) or not rules or len(rules) != len(set(rules)) or
        not set(rules) <= RULES):
        raise ValueError('Unknown, duplicate or empty rules')
    if not isinstance(policy['max_findings'], int) or isinstance(policy['max_findings'], bool) or not 1 <= policy['max_findings'] <= MAX_FINDINGS:
        raise ValueError('Invalid finding budget')
    if not isinstance(policy['max_graph_modules'], int) or isinstance(policy['max_graph_modules'], bool) or not 1 <= policy['max_graph_modules'] <= MAX_GRAPH_MODULES:
        raise ValueError('Invalid graph query budget')
    return policy, sha(data)


def _mutable(node: ast.AST) -> bool:
    return isinstance(node, (ast.List, ast.Dict, ast.Set)) or (
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and
        node.func.id in ('list', 'dict', 'set') and not node.args and not node.keywords
    )


def _source_span(node: ast.AST) -> dict:
    return {'line': node.lineno, 'column': node.col_offset,
            'end_line': getattr(node, 'end_lineno', node.lineno),
            'end_column': getattr(node, 'end_col_offset', node.col_offset)}


class _Scanner(ast.NodeVisitor):
    def __init__(self, file: str, source_hash: str, enabled: set[str]):
        self.file = file
        self.source_hash = source_hash
        self.enabled = enabled
        self.hits: list[dict] = []
        self.context: list[str] = []

    def _hit(self, rule: str, node: ast.AST, *, witness: dict | None = None) -> None:
        if rule not in self.enabled:
            return
        span = _source_span(node)
        # Identity binds source, rule, occurrence and full audited source bytes.
        ident = sha(canonical([self.file, self.source_hash, rule, span, self.context, witness or {}]))[:32]
        self.hits.append({'id':'ae12-'+ident, 'rule':rule, 'file':self.file,
                          'module':module_name(self.file), 'source_sha256':self.source_hash,
                          'span':span, 'lexical_context':list(self.context),
                          'witness':witness or {}, 'classification':'source_pattern_requires_review'})

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        defaults = list(node.args.defaults) + [d for d in node.args.kw_defaults if d is not None]
        for index, default in enumerate(defaults):
            if _mutable(default):
                self._hit('mutable_default', default, witness={'function':node.name,'default_index':index})
        self.context.append(node.name)
        self.generic_visit(node)
        self.context.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is None:
            self._hit('bare_except', node)
        significant = [s for s in node.body if not (isinstance(s, ast.Expr) and
                       isinstance(s.value, ast.Constant) and isinstance(s.value.value,str))]
        if len(significant) == 1 and isinstance(significant[0], ast.Pass):
            self._hit('swallowed_exception', significant[0], witness={'bare':node.type is None})
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try | ast.TryStar) -> None:
        for stmt in node.finalbody:
            # Direct return statement in finally overrides in-flight return/exception.
            # Conditional and nested-function cases are intentionally not inferred.
            if isinstance(stmt, ast.Return):
                self._hit('finally_return', stmt)
        self.generic_visit(node)

    visit_TryStar = visit_Try

    def visit_Dict(self, node: ast.Dict) -> None:
        seen: dict[Any, ast.AST] = {}
        for key in node.keys:
            if key is None:
                continue
            try:
                literal = ast.literal_eval(key)
                hash(literal)
            except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                continue
            # Python equality semantics intentionally catch True/1 and 1/1.0 collisions.
            if literal in seen:
                earlier = seen[literal]
                self._hit('duplicate_dict_key', key, witness={'earlier_line':earlier.lineno,
                          'earlier_column':earlier.col_offset})
            else:
                seen[literal] = key
        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        if any(isinstance(n, ast.Call) for n in ast.walk(node.test)):
            self._hit('assert_call', node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if (isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
            and node.func.value.id == 'subprocess' and
            node.func.attr in ('run','Popen','check_call','check_output')):
            for kw in node.keywords:
                if kw.arg == 'shell' and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    self._hit('subprocess_shell', node, witness={'api':node.func.attr})
        self.generic_visit(node)


def _scan_file(path: str, raw: bytes, encoding: str, rules: set[str]) -> list[dict]:
    tree = ast.parse(raw.decode(encoding), filename=path)
    visitor = _Scanner(path,sha(raw),rules)
    visitor.visit(tree)
    return visitor.hits


def _checked_source(root: Path, path: str, expected_hash: str) -> bytes:
    p = root / path
    _no_symlink_components(p)
    data = p.read_bytes()
    if sha(data) != expected_hash:
        raise ValueError('AE-01 source manifest mismatch: ' + path)
    return data


def build_report(ae01_output: Path | str, source_root: Path | str, policy_file: Path | str,
                 *, generation_id: str | None = None, runtime_log: Path | str | None = None) -> dict:
    policy, policy_sha = load_policy(policy_file)
    root = Path(source_root).absolute()
    _no_symlink_components(root)
    generation = load_generation(ae01_output, generation_id, source_root=root)
    listed = {r['path']:r for r in generation.manifest['files'] if r['status']=='included'}
    selected = sorted(listed) if policy['paths']==['*'] else sorted(policy['paths'])
    issues: list[str] = []
    if len(selected)>MAX_SOURCE_FILES:
        raise ValueError('Selected source scope exceeds bounded 2500-file limit')
    absent = sorted(set(selected)-set(listed))
    if absent:
        issues.append('policy_source_missing_or_not_included')
    findings: list[dict] = []
    coverage = []
    for path in selected:
        row = listed.get(path)
        if row is None:
            coverage.append({'file':path,'status':'not_audited','reason':'not_in_verified_manifest'})
            continue
        data = _checked_source(root,path,row['sha256'])
        hits = _scan_file(path,data,row['encoding'],set(policy['rules']))
        for hit in hits:
            if len(findings) >= policy['max_findings']:
                issues.append('finding_budget_exceeded')
                break
            findings.append(hit)
        coverage.append({'file':path,'sha256':row['sha256'],'status':'scanned',
                         'pattern_observations':len(hits)})
        if 'finding_budget_exceeded' in issues:
            break
    if generation.snapshot.assurance_completeness != 'complete_within_declared_scope':
        issues.append('ae01_source_or_policy_assurance_incomplete')
    findings.sort(key=lambda h:(h['file'],h['span']['line'],h['span']['column'],h['rule'],h['id']))
    modules = sorted({f['module'] for f in findings})
    if len(modules)>policy['max_graph_modules']:
        issues.append('graph_module_budget_exceeded')
    _, graph = _graph_inputs(generation)
    analyzer = GraphAnalysisEngine(graph)
    analyses = []
    for mod in modules[:policy['max_graph_modules']]:
        node = 'module:'+mod
        if graph.get_node(node) is None:
            issues.append('observed_module_missing_from_verified_graph')
            continue
        result = analyzer.execute(GraphQuery('ae12:'+mod,QueryType.DEPENDENCY,[node],
                            {'max_depth':1, 'relation_types':['IMPORTS']}))
        analyses.append({'module':mod,'analysis_id':result.analysis_id,
                         'graph_fingerprint':result.graph_fingerprint,
                         'observation_count':len(result.observations)})
    runtime = None
    if runtime_log is not None:
        correlated = correlate_runtime(ae01_output,runtime_log,root,
                                       generation_id=generation.snapshot.generation_id)
        source_signal = {f['source_path'] for f in correlated['observations']
                         if f.get('match_strategy') in ('exact','suffix') and f.get('source_path')}
        runtime = {'log_sha256':correlated['log_sha256'],
                   'investigation_sha256':correlated['record_sha256'],
                   'assurance_status':correlated['assurance_status'],
                   'observed_paths':sorted(source_signal),
                   'failure_signal_classes':sorted({s['exception_class'] for s in correlated['failure_signals']})}
        if correlated['assurance_status']!='bounded_correlation':
            issues.append('runtime_correlation_inconclusive')
        for f in findings:
            f['runtime_co_observed_module'] = f['file'] in source_signal
        # Co-observation is NOT a causal association.
    issues=sorted(set(issues))
    body = {'schema':SCHEMA, 'ae01_generation':generation.snapshot.generation_id,
            'ae01_seal_sha256':generation.snapshot.publication_seal_hash,
            'source_digest':generation.snapshot.source_digest,
            'policy_graph_fingerprint':generation.report['policy_graph_fingerprint'],
            'policy_sha256':policy_sha,'scope':selected,
            'rule_coverage':[{'rule':r,'status':'evaluated_on_selected_parsed_sources'}
                             for r in sorted(policy['rules'])],
            'source_coverage':coverage,'graph_analyses':analyses,
            'findings':findings,'runtime':runtime,'issues':issues,
            'assurance_status':'inconclusive' if issues else 'bounded_observations',
            'conclusion':'programming_pattern_observations_not_verified_defects_or_root_causes'}
    body['record_sha256'] = sha(canonical(body))
    return body


def verify_report(report: dict, ae01_output: Path | str, source_root: Path | str,
                  policy_file: Path | str, *, runtime_log: Path | str | None = None) -> dict:
    if not isinstance(report,dict) or report.get('schema')!=SCHEMA:
        raise ValueError('Invalid AE-12 report schema')
    repeat = build_report(ae01_output,source_root,policy_file,
                          generation_id=report.get('ae01_generation'),runtime_log=runtime_log)
    if canonical(repeat)!=canonical(report):
        raise ValueError('AE-12 report differs from independent source, policy and graph replay')
    return {'verified':True,'observations':len(report['findings']),
            'assurance_status':report['assurance_status'],'record_sha256':report['record_sha256']}
