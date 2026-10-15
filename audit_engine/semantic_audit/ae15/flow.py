"""AE-15/G9.17: source-bound, bounded, conservative intraprocedural *may* flow.

No target source is executed. The relation MAY_FLOW_TO is an over-approximation
for a deliberately restricted Python statement subset; it is NOT a feasible
execution, dispatch, exception, or security proof. All unsupported controls are
reported, and a partial analysis may not be interpreted as a clean verdict.
"""
from __future__ import annotations

import ast
import hashlib
import io
import tokenize
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from audit_engine.semantic_audit.ae01.source import module_name
from audit_engine.semantic_audit.ae14.lexical import LexicalProgram, Scope
from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph.analysis.identity import graph_fingerprint

VERSION = 'ae15/flow/v1'


class FlowLimitExceeded(ValueError):
    """No partial result is published when source or fixed-point budget is exceeded."""


def _walk_expression(node: ast.AST):
    """Exclude deferred nested code and comprehension internals from current scope."""
    if isinstance(node, (ast.Lambda, ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
        if isinstance(node, ast.Lambda):
            for expr in (*node.args.defaults, *node.args.kw_defaults):
                if expr is not None:
                    yield from _walk_expression(expr)
        elif node.generators:
            yield from _walk_expression(node.generators[0].iter)
        return
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for expr in (*node.decorator_list, *node.args.defaults, *node.args.kw_defaults):
            if expr is not None:
                yield from _walk_expression(expr)
        return
    if isinstance(node, ast.ClassDef):
        for expr in (*node.decorator_list, *node.bases):
            yield from _walk_expression(expr)
        for keyword in node.keywords:
            yield from _walk_expression(keyword.value)
        return
    yield node
    for child in ast.iter_child_nodes(node):
        yield from _walk_expression(child)


def _effects(node: ast.AST) -> tuple[list[ast.Name], list[ast.Name], bool]:
    """Reads, writes and an expression-precision gap flag (not runtime effects)."""
    nodes = list(_walk_expression(node))
    reads = [n for n in nodes if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)]
    writes = [n for n in nodes if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del))]
    gap = any(isinstance(n, (ast.Yield, ast.YieldFrom, ast.Await, ast.NamedExpr, ast.IfExp, ast.BoolOp)) for n in nodes)
    gap |= any(isinstance(n, (ast.Lambda, ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp))
               for n in ast.walk(node))
    return reads, writes, bool(gap)


@dataclass
class FlowScope:
    scope: Scope
    source: str
    sha256: str
    lexical: LexicalProgram
    max_points: int
    max_iterations: int
    graph: SemanticGraph
    nodes: dict[str, dict] = field(default_factory=dict)
    links: list[dict] = field(default_factory=list)
    definitions: dict[str, dict] = field(default_factory=dict)
    uses: list[dict] = field(default_factory=list)
    gaps: list[dict] = field(default_factory=list)
    _ordinal: int = 0
    _loop: list[tuple[str, str]] = field(default_factory=list)

    def __post_init__(self):
        self.prefix = f'flow:{self.source}:{self.sha256}:{self.scope.occurrence_key}'
        self.entry = self._point('entry', self.scope.node)
        self.exit = self._point('exit', self.scope.node)
        self._parameter_defs()

    def _point(self, kind: str, ast_node: ast.AST, *, expr: ast.AST | None = None,
               extra_names: tuple[str, ...] = ()) -> str:
        self._ordinal += 1
        if self._ordinal > self.max_points:
            raise FlowLimitExceeded('AE-15 per-scope point budget exceeded')
        point = f'{self.prefix}:p{self._ordinal}'
        n = expr or ast_node
        row = {'id': point, 'kind': kind, 'scope': self.scope.occurrence_key,
               'line': getattr(n, 'lineno', getattr(ast_node, 'lineno', 0)),
               'column': getattr(n, 'col_offset', 0), 'source_sha256': self.sha256,
               'defs': [], 'uses': []}
        self.nodes[point] = row
        self.graph.add_node(SemanticNode(point, 'ControlPoint',
                                        {'kind': kind, 'scope': self.scope.qualified_name},
                                        {'source_id': self.source, 'source_sha256': self.sha256,
                                         'line': row['line'], 'column': row['column'],
                                         'scope_occurrence': self.scope.occurrence_key}))
        if expr is not None or kind not in ('entry','exit','join'):
            self._add_effects(point, n, extra_names)
        return point

    def _gap(self, kind: str, node: ast.AST):
        self.gaps.append({'kind': kind, 'source_id': self.source,
                          'line': getattr(node, 'lineno', 0),
                          'scope': self.scope.occurrence_key})

    def _parameter_defs(self):
        node = self.scope.node
        if self.scope.kind not in ('function', 'lambda'):
            return
        args = node.args
        names = [a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)]
        names += [a.arg for a in (args.vararg, args.kwarg) if a]
        for name in names:
            self._definition(self.entry, name, 0, 'parameter')

    def _definition(self, point: str, name: str, line: int, kind: str):
        did = f'{point}:def:{name}'
        if did not in self.definitions:
            self.definitions[did] = {'id': did, 'name': name, 'point': point,
                                      'line': line, 'kind': kind, 'scope': self.scope.occurrence_key}
            self.nodes[point]['defs'].append(did)
            self.graph.add_node(SemanticNode(did, 'Definition', {'name': name, 'kind': kind},
                                             {'source_id': self.source, 'source_sha256': self.sha256,
                                              'line': line, 'scope_occurrence': self.scope.occurrence_key}))
            self.graph.add_edge(SemanticEdge(point, did, 'DEFINES_AT',
                                             metadata={'source_id': self.source}))

    def _add_effects(self, point: str, expr: ast.AST, extra_names: tuple[str, ...] = ()):
        reads, writes, gap = _effects(expr)
        if isinstance(expr, ast.AnnAssign) and expr.value is None:
            # CPython annotation-only local declarations do not assign values.
            writes = [w for w in writes if w is not expr.target]
        if isinstance(expr, ast.AugAssign) and isinstance(expr.target, ast.Name):
            # x += y reads the old x before writing the new x.
            reads = [expr.target, *reads]
        if isinstance(expr, ast.ImportFrom) and any(a.name == '*' for a in expr.names):
            self._gap('star_import_bindings_unresolved',expr)
        if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and
               n.func.id in {'exec','eval','locals','globals','vars','setattr','delattr','__import__'}
               for n in _walk_expression(expr)):
            self._gap('dynamic_namespace_or_reflection_unsupported',expr)
        if gap:
            self._gap('expression_control_or_deferred_scope_not_modeled', expr)
        for name in extra_names:
            self._definition(point, name, getattr(expr, 'lineno', 0), 'definition')
        for i, item in enumerate(reads):
            owner, _ = self.lexical.resolve(item.id, item)
            # Closures and imported/global names are not proved by this local model.
            owner_key = owner.occurrence_key if owner else None
            local = owner is self.scope
            uid = f'{point}:use:{i}:{item.id}'
            row = {'id': uid, 'name': item.id, 'point': point,
                   'line': item.lineno, 'column': item.col_offset,
                   'binding_scope': owner_key, 'local': local,
                   'may_definitions': [], 'status': 'unresolved'}
            self.uses.append(row)
            self.nodes[point]['uses'].append(uid)
            self.graph.add_node(SemanticNode(uid, 'VariableUse', {'name': item.id},
                                             {'source_id': self.source, 'source_sha256': self.sha256,
                                              'line': item.lineno, 'scope_occurrence': self.scope.occurrence_key}))
            self.graph.add_edge(SemanticEdge(point, uid, 'USES_AT',
                                             metadata={'source_id': self.source}))
        for item in writes:
            if isinstance(item.ctx, ast.Store):
                if self.lexical.resolve(item.id, item)[0] is self.scope:
                    self._definition(point, item.id, item.lineno, 'assignment')
            elif isinstance(item.ctx, ast.Del):
                # deletion kills local definitions; it does not create a value.
                if self.lexical.resolve(item.id, item)[0] is self.scope:
                    self.nodes[point].setdefault('kills', []).append(item.id)

    def _edge(self, frm: str, to: str, label: str):
        row = {'from': frm, 'to': to, 'condition': label}
        if row not in self.links:
            self.links.append(row)
            self.graph.add_edge(SemanticEdge(frm, to, 'MAY_FLOW_TO',
                                             {'condition': label},
                                             {'source_id': self.source, 'source_sha256': self.sha256,
                                              'scope_occurrence': self.scope.occurrence_key}))

    def _connect(self, incoming: list[tuple[str,str]], target: str):
        for frm, label in incoming:
            self._edge(frm,target,label)

    def _seq(self, body: list[ast.stmt], incoming: list[tuple[str,str]]) -> list[tuple[str,str]]:
        for stmt in body:
            # Unreachable lexical statements are still recorded, but do not
            # reconnect to reachable points through an invented path.
            incoming = self._stmt(stmt, incoming)
        return incoming

    def _stmt(self, s: ast.stmt, incoming: list[tuple[str,str]]) -> list[tuple[str,str]]:
        if isinstance(s, ast.If):
            head = self._point('if_test', s, expr=s.test)
            self._connect(incoming, head)
            yes = self._seq(s.body, [(head, 'true')])
            no = self._seq(s.orelse, [(head, 'false')]) if s.orelse else [(head, 'false')]
            after = self._point('join', s)
            self._connect(yes+no, after)
            return [(after, 'next')]
        if isinstance(s, (ast.While, ast.For, ast.AsyncFor)):
            if isinstance(s, ast.AsyncFor):
                self._gap('AsyncFor_suspension_and_scheduler_unsupported',s)
            head = self._point('loop_test', s, expr=s.test if isinstance(s, ast.While) else s.iter)
            self._connect(incoming, head)
            after = self._point('join', s)
            self._loop.append((head, after))
            if isinstance(s, (ast.For, ast.AsyncFor)):
                iteration = self._point('for_iteration_target', s, expr=s.target)
                self._edge(head, iteration, 'iteration_possible')
                body_in = [(iteration, 'next')]
            else:
                body_in = [(head, 'true')]
            done = self._seq(s.body, body_in)
            self._connect([(p, 'next_iteration') for p,_ in done], head)
            self._loop.pop()
            else_done = self._seq(s.orelse, [(head, 'zero_or_finished')]) if s.orelse else [(head,'zero_or_finished')]
            self._connect(else_done, after)
            return [(after, 'next')]
        if isinstance(s, (ast.Try, ast.TryStar, ast.With, ast.AsyncWith, ast.Match)):
            point = self._point('opaque_control', s)
            self._connect(incoming, point)
            self._gap(type(s).__name__ + '_control_semantics_unsupported', s)
            # Preserve a MAY-fallthrough but do not assert knowledge of inner paths.
            return [(point, 'possible_fallthrough')]
        kind = type(s).__name__
        # Bindings for named imports and function/class definitions are created
        # at their statement, not assigned by AST Name(Store) nodes.
        names: list[str] = []
        if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [s.name]
        elif isinstance(s, (ast.Import, ast.ImportFrom)):
            names = [a.asname or (a.name.partition('.')[0] if isinstance(s,ast.Import) else a.name)
                     for a in s.names if a.name != '*']
        point = self._point(kind, s, extra_names=tuple(n for n in names if n in self.scope.bindings))
        self._connect(incoming, point)
        if isinstance(s, (ast.Return, ast.Raise)):
            self._edge(point, self.exit, 'return' if isinstance(s,ast.Return) else 'exception_escape_possible')
            return []
        if isinstance(s, (ast.Break, ast.Continue)):
            if not self._loop:
                self._gap('jump_without_modeled_loop', s)
            else:
                header, after = self._loop[-1]
                self._edge(point, after if isinstance(s,ast.Break) else header,
                           'break' if isinstance(s,ast.Break) else 'continue')
            return []
        # `assert` can raise, ordinary calls may raise: never claim must-fallthrough.
        return [(point, 'possible_next')]

    def build(self, body: list[ast.stmt]):
        outgoing = self._seq(body, [(self.entry,'entry')])
        self._connect(outgoing, self.exit)
        self._solve()
        return {'source': self.source, 'sha256': self.sha256,
                'scope': self.scope.qualified_name,
                'scope_occurrence': self.scope.occurrence_key,
                'scope_kind': self.scope.kind,
                'entry': self.entry, 'exit': self.exit,
                'control_points': list(self.nodes.values()), 'may_flow': self.links,
                'definitions': list(self.definitions.values()), 'uses': self.uses,
                'gaps': self.gaps,
                'completeness': 'partial' if self.gaps else 'bounded_may_flow_only'}

    def _solve(self):
        pred: dict[str, set[str]] = defaultdict(set)
        reach: set[str] = {self.entry}
        for row in self.links:
            pred[row['to']].add(row['from'])
        queue = deque([self.entry])
        adj: dict[str,list[str]] = defaultdict(list)
        for row in self.links: adj[row['from']].append(row['to'])
        while queue:
            u=queue.popleft()
            for v in adj[u]:
                if v not in reach:
                    reach.add(v);queue.append(v)
        defs = {p: set(row['defs']) for p,row in self.nodes.items()}
        killed = {p: {self.definitions[d]['name'] for d in defs[p]} | set(row.get('kills',[]))
                  for p,row in self.nodes.items()}
        outset = {p: set() for p in self.nodes}
        inset = {p: set() for p in self.nodes}
        possible_names = {d['name'] for d in self.definitions.values()}
        must_in = {p: set(possible_names) if p != self.entry else set() for p in self.nodes}
        must_out = {p: set(possible_names) if p != self.entry else set() for p in self.nodes}
        for count in range(self.max_iterations):
            changed=False
            for p in self.nodes:
                if p not in reach:continue
                newin=set().union(*(outset[q] for q in pred[p] if q in reach)) if p!=self.entry else set()
                newout={d for d in newin if self.definitions[d]['name'] not in killed[p]} | defs[p]
                mnewin=(set.intersection(*(must_out[q] for q in pred[p] if q in reach))
                        if p!=self.entry and any(q in reach for q in pred[p]) else set())
                mnewout=(mnewin - set(self.nodes[p].get('kills',[]))) | {self.definitions[d]['name'] for d in defs[p]}
                if (newin != inset[p] or newout != outset[p] or mnewin != must_in[p] or mnewout != must_out[p]):
                    inset[p],outset[p],must_in[p],must_out[p]=newin,newout,mnewin,mnewout
                    changed=True
            if not changed:break
        else:
            raise FlowLimitExceeded('AE-15 fixed-point iteration budget exceeded')
        for row in self.uses:
            p=row['point'];name=row['name']
            if p not in reach:
                row['status']='unreachable_on_modeled_paths';continue
            if not row['local']:
                row['status']='external_or_unknown_binding';continue
            supporting=sorted(d for d in inset[p] if self.definitions[d]['name']==name)
            row['may_definitions']=supporting
            if self.gaps:
                row['status']='partial_unsupported_control'
            elif not supporting:
                row['status']='possibly_unbound'
            elif name in must_in[p]:
                row['status']='may_reach_definitions'
            else:
                row['status']='possibly_unbound'
            for did in supporting:
                self.graph.add_edge(SemanticEdge(did,row['id'],'MAY_REACH',
                                                 metadata={'source_id':self.source,
                                                           'source_sha256':self.sha256,
                                                           'scope_occurrence':self.scope.occurrence_key}))


def analyze_snapshot(sources: dict[str, bytes], manifest: dict, *, max_points_per_scope: int = 3000,
                     max_iterations: int = 5000, max_total_points: int = 30000) -> tuple[dict, SemanticGraph]:
    """Consume *already inventoried* exact bytes; recheck membership, hashes and encoding.

    The output is a fact report and a typed canonical SemanticGraph projection.
    They are observations, NOT authorized verifier receipts or findings.
    """
    if min(max_points_per_scope,max_iterations,max_total_points) < 1:
        raise ValueError('All analysis budgets must be positive')
    manifest_rows={r['path']:r for r in manifest.get('files',[]) if r.get('status')=='included'}
    if (len(manifest_rows)!=sum(r.get('status')=='included' for r in manifest.get('files',[]))
        or set(manifest_rows)!=set(sources)):
        raise ValueError('Source inventory membership mismatch')
    graph=SemanticGraph();reports=[];total=0
    for path in sorted(sources):
        if not path.endswith('.py') or path.startswith('/') or '..' in path.split('/') or '\\' in path:
            raise ValueError('Unsafe source path')
        data=sources[path]; row=manifest_rows[path]
        digest=hashlib.sha256(data).hexdigest()
        if row.get('sha256')!=digest:raise ValueError('Source checksum mismatch')
        encoding,_=tokenize.detect_encoding(io.BytesIO(data).readline)
        if row.get('encoding')!=encoding:raise ValueError('Source encoding mismatch')
        tree=ast.parse(data.decode(encoding),filename=path)
        lex=LexicalProgram(tree,module_name(path))
        graph.add_node(SemanticNode('source:'+path,'SourceFile',{'sha256':digest}, {'source_id':path}))
        scopes=[lex.root,*sorted(lex.children.values(),key=lambda x:(getattr(x.node,'lineno',0),getattr(x.node,'col_offset',0),x.occurrence_key))]
        for scope in scopes:
            if scope.kind=='comprehension':
                continue  # inner iterable/body semantics intentionally unresolved
            body=(tree.body if scope.kind=='module' else
                  scope.node.body if scope.kind in ('function','class') else [])
            if scope.kind=='lambda':
                # Lambda execution is deferred; expression itself has no statement CFG.
                continue
            if not isinstance(body,list):body=[body]
            if total+len(body)+2>max_total_points:raise FlowLimitExceeded('AE-15 total point budget exceeded')
            analysis=FlowScope(scope,path,digest,lex,max_points_per_scope,max_iterations,graph)
            if isinstance(scope.node, ast.AsyncFunctionDef):
                analysis._gap('AsyncFunction_scheduler_semantics_unsupported',scope.node)
            report=analysis.build(body)
            total+=len(analysis.nodes)
            if total>max_total_points:raise FlowLimitExceeded('AE-15 total point budget exceeded')
            graph.add_edge(SemanticEdge('source:'+path,analysis.entry,'HAS_FLOW_SCOPE',
                                         metadata={'source_id':path,'source_sha256':digest}))
            reports.append(report)
    fingerprint=graph_fingerprint(graph)
    return {'schema':VERSION,'sources':{p:hashlib.sha256(sources[p]).hexdigest() for p in sorted(sources)},
            'scopes':reports,'graph_fingerprint':fingerprint,
            'assurance': 'partial' if any(s['gaps'] for s in reports) or manifest.get('summary',{}).get('error') else 'bounded_may_flow_only',
            'disclaimer':'No runtime feasibility, dispatch proof, exception completeness, or clean-code conclusion'},graph
