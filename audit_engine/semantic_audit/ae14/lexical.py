"""AE-14: conservative Python lexical-binding facts, not dispatch or CFG proof.

This phase does not import, evaluate, or execute target source. AST-node membership
is local to one source snapshot. Candidate callees are never verified invocations.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Binding:
    name: str
    kind: str
    qualified_name: str | None = None
    imported: str | None = None
    conditional: bool = False


@dataclass
class Scope:
    kind: str
    qualified_name: str
    parent: 'Scope | None'
    node: ast.AST
    bindings: dict[str, list[Binding]] = field(default_factory=dict)
    globals: set[str] = field(default_factory=set)
    nonlocals: set[str] = field(default_factory=set)

    @property
    def occurrence_key(self) -> str:
        if self.kind == 'module':
            return self.qualified_name
        return f'{self.qualified_name}@{getattr(self.node, "lineno", 0)}:{getattr(self.node, "col_offset", 0)}'

    def add(self, binding: Binding) -> None:
        self.bindings.setdefault(binding.name, []).append(binding)


class LexicalProgram(ast.NodeVisitor):
    """Pre-index lexical scopes and binding declarations, including shadowing.

    Assignment identities deliberately have no reaching-definition claims.
    Every competing binder weakens candidate resolution even when it occurs
    after the AST node: in a Python function a local declaration is scope-wide.
    """

    def __init__(self, tree: ast.Module, module: str):
        self.module = module
        self.root = Scope('module', module, None, tree)
        self.current = self.root
        self.owners: dict[ast.AST, Scope] = {}
        self.children: dict[ast.AST, Scope] = {}
        self.conditional_depth = 0
        self.visit(tree)

    def visit(self, node: ast.AST):
        self.owners[node] = self.current
        return super().visit(node)

    def _bind(self, name: str, kind: str, *, qualified: str | None = None, imported: str | None = None):
        self.current.add(Binding(name, kind, qualified, imported, self.conditional_depth > 0))

    def _scope(self, node: ast.AST, kind: str, label: str) -> Scope:
        child = Scope(kind, self.current.qualified_name + '.' + label, self.current, node)
        self.children[node] = child
        return child

    def _enter(self, child: Scope, body: list[ast.AST]):
        prior = self.current
        self.current = child
        self.owners[child.node] = child
        try:
            for statement in body:
                self.visit(statement)
        finally:
            self.current = prior

    def _arguments(self, args: ast.arguments):
        for argument in [*args.posonlyargs, *args.args, *args.kwonlyargs]:
            self._bind(argument.arg, 'parameter')
        for argument in (args.vararg, args.kwarg):
            if argument:
                self._bind(argument.arg, 'parameter')

    def _outer_signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
        # Default expressions and decorators execute in the *enclosing* scope.
        if not isinstance(node, ast.Lambda):
            for expr in node.decorator_list:
                self.visit(expr)
        for expr in [*node.args.defaults, *node.args.kw_defaults]:
            if expr is not None:
                self.visit(expr)
        # Annotation evaluation depends on future annotations and Python version.
        # Record its source ownership, but never promote it into callable binding.
        for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
            if arg.annotation:
                self.visit(arg.annotation)
        for arg in (node.args.vararg, node.args.kwarg):
            if arg is not None and arg.annotation:
                self.visit(arg.annotation)
        if not isinstance(node, ast.Lambda):
            if node.returns:
                self.visit(node.returns)
            for arg in getattr(node, 'type_params', ()):
                self.visit(arg)

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        qual = self.current.qualified_name + '.' + node.name
        self._bind(node.name, 'function', qualified=qual)
        self._outer_signature(node)
        child = self._scope(node, 'function', node.name)
        prior = self.current
        self.current = child
        self._arguments(node.args)
        self.current = prior
        self._enter(child, node.body)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef):
        qual = self.current.qualified_name + '.' + node.name
        self._bind(node.name, 'class', qualified=qual)
        for expr in [*node.decorator_list, *node.bases]:
            self.visit(expr)
        for keyword in node.keywords:
            self.visit(keyword.value)
        for arg in getattr(node, 'type_params', ()):
            self.visit(arg)
        self._enter(self._scope(node, 'class', node.name), node.body)

    def visit_Lambda(self, node: ast.Lambda):
        self._outer_signature(node)
        child = self._scope(node, 'lambda', f'<lambda>@{node.lineno}:{node.col_offset}')
        prior = self.current
        self.current = child
        self._arguments(node.args)
        self.current = prior
        self._enter(child, [node.body])

    def _comprehension(self, node: ast.AST, label: str, result: list[ast.AST]):
        # Only the outermost iterable is evaluated outside comprehension scope.
        generators = node.generators  # type: ignore[attr-defined]
        if generators:
            self.visit(generators[0].iter)
        child = self._scope(node, 'comprehension', f'<{label}>@{node.lineno}:{node.col_offset}')
        body: list[ast.AST] = []
        for i, gen in enumerate(generators):
            body.append(gen.target)
            if i:
                body.append(gen.iter)
            body.extend(gen.ifs)
        self._enter(child, [*body, *result])

    def visit_ListComp(self, node: ast.ListComp):
        self._comprehension(node, 'listcomp', [node.elt])

    def visit_SetComp(self, node: ast.SetComp):
        self._comprehension(node, 'setcomp', [node.elt])

    def visit_GeneratorExp(self, node: ast.GeneratorExp):
        self._comprehension(node, 'genexpr', [node.elt])

    def visit_DictComp(self, node: ast.DictComp):
        self._comprehension(node, 'dictcomp', [node.key, node.value])

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            name = alias.asname or alias.name.partition('.')[0]
            imported = alias.name if alias.asname else alias.name.partition('.')[0]
            self._bind(name, 'import', imported=imported)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        for alias in node.names:
            if alias.name == '*':
                self._bind('*', 'import_star')
                continue
            self._bind(alias.asname or alias.name, 'import',
                       imported='.' * node.level + ((node.module + '.') if node.module else '') + alias.name)

    def visit_Global(self, node: ast.Global):
        self.current.globals.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal):
        self.current.nonlocals.update(node.names)

    def visit_Name(self, node: ast.Name):
        if isinstance(node.ctx, ast.Store):
            self._bind(node.id, 'assignment')
        elif isinstance(node.ctx, ast.Del):
            self._bind(node.id, 'deletion')

    def visit_Attribute(self, node: ast.Attribute):
        # A monkey-patched import alias cannot establish stable attributes.
        if isinstance(node.ctx, (ast.Store, ast.Del)) and isinstance(node.value, ast.Name):
            self._bind(node.value.id, 'attribute_mutation')
        self.visit(node.value)

    def visit_If(self, node: ast.If):
        self.visit(node.test)
        self.conditional_depth += 1
        try:
            for stmt in [*node.body, *node.orelse]:
                self.visit(stmt)
        finally:
            self.conditional_depth -= 1

    def visit_For(self, node: ast.For | ast.AsyncFor):
        self.visit(node.iter)
        self.conditional_depth += 1
        try:
            self.visit(node.target)
            for stmt in [*node.body, *node.orelse]:
                self.visit(stmt)
        finally:
            self.conditional_depth -= 1

    visit_AsyncFor = visit_For

    def visit_While(self, node: ast.While):
        self.visit(node.test)
        self.conditional_depth += 1
        try:
            for stmt in [*node.body, *node.orelse]:
                self.visit(stmt)
        finally:
            self.conditional_depth -= 1

    def visit_Try(self, node: ast.Try):
        self.conditional_depth += 1
        try:
            for stmt in [*node.body, *node.handlers, *node.orelse, *node.finalbody]:
                self.visit(stmt)
        finally:
            self.conditional_depth -= 1

    visit_TryStar = visit_Try

    def visit_Match(self, node: ast.Match):
        self.visit(node.subject)
        self.conditional_depth += 1
        try:
            for case in node.cases:
                self.visit(case)
        finally:
            self.conditional_depth -= 1

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        if node.type:
            self.visit(node.type)
        if node.name:
            self._bind(node.name, 'exception_target')
        for stmt in node.body:
            self.visit(stmt)
        if node.name:
            self._bind(node.name, 'deletion')

    def visit_MatchAs(self, node: ast.MatchAs):
        if node.pattern:
            self.visit(node.pattern)
        if node.name:
            self._bind(node.name, 'pattern_target')

    def visit_MatchStar(self, node: ast.MatchStar):
        if node.name:
            self._bind(node.name, 'pattern_target')

    def visit_MatchMapping(self, node: ast.MatchMapping):
        for value in node.keys:
            self.visit(value)
        for pattern in node.patterns:
            self.visit(pattern)
        if node.rest:
            self._bind(node.rest, 'pattern_target')

    def visit_NamedExpr(self, node: ast.NamedExpr):
        # Assignment expressions inside comprehensions bind enclosing scope;
        # declaring both possible scopes prevents false lexical certainty.
        if self.current.kind == 'comprehension' and isinstance(node.target, ast.Name):
            parent = self.current.parent
            if parent:
                parent.add(Binding(node.target.id, 'assignment', conditional=True))
        self.generic_visit(node)

    def _owner(self, node: ast.AST) -> Scope:
        return self.owners[node]

    def _lookup(self, name: str, scope: Scope) -> tuple[Scope | None, list[Binding]]:
        original = scope
        if name in scope.globals:
            scope = self.root
        elif name in scope.nonlocals:
            scope = scope.parent or self.root
            while scope is not self.root and scope.kind == 'class':
                scope = scope.parent or self.root
        while scope:
            # Class namespace is not a closure cell for methods.
            if scope.kind == 'class' and original is not scope:
                scope = scope.parent
                continue
            if name in scope.bindings:
                return scope, scope.bindings[name]
            if '*' in scope.bindings:
                # Import-star may shadow unknown names.
                return scope, [Binding(name, 'star_unknown')]
            scope = scope.parent
        return None, []

    def resolve(self, name: str, node: ast.AST) -> tuple[Scope | None, list[Binding]]:
        return self._lookup(name, self._owner(node))

    def stable_import(self, name: str, node: ast.AST, target: str) -> bool:
        _, bindings = self.resolve(name, node)
        return len(bindings) == 1 and bindings[0].kind == 'import' and not bindings[0].conditional and bindings[0].imported == target

    def type_checking(self, test: ast.AST) -> bool:
        if isinstance(test, ast.Name):
            return self.stable_import(test.id, test, 'typing.TYPE_CHECKING')
        if (isinstance(test, ast.Attribute) and test.attr == 'TYPE_CHECKING' and
                isinstance(test.value, ast.Name)):
            return self.stable_import(test.value.id, test.value, 'typing')
        return False

    def classify_call(self, node: ast.Call) -> dict:
        from audit_engine.semantic_audit.ae01.source import _call_name
        spelling = _call_name(node.func)
        receiver, _, attr = spelling.rpartition('.')
        scope = self._owner(node)
        resolution, candidates, reason = 'unresolved', [], 'unknown_runtime_target'
        dynamic = False
        if isinstance(node.func, ast.Name):
            owner, bindings = self.resolve(spelling, node.func)
            if len(bindings) == 1 and not bindings[0].conditional:
                binding = bindings[0]
                if binding.kind in ('function', 'class') and binding.qualified_name:
                    resolution, candidates, reason = 'candidate', [binding.qualified_name], 'lexical_definition_candidate'
                elif binding.kind == 'import' and binding.imported and not binding.imported.startswith('.'):
                    resolution, candidates, reason = 'candidate', [binding.imported], 'lexical_import_candidate'
                elif binding.kind in ('parameter', 'assignment', 'deletion', 'exception_target', 'attribute_mutation', 'pattern_target'):
                    reason = 'local_or_enclosing_shadow'
            elif bindings:
                reason = 'ambiguous_or_conditional_binding'
            else:
                reason = 'unbound_or_builtin_name'
            dynamic = ((spelling == '__import__' and not bindings) or
                       (len(bindings) == 1 and bindings[0].kind == 'import' and
                        not bindings[0].conditional and bindings[0].imported == 'importlib.import_module'))
        elif (isinstance(node.func, ast.Attribute) and
              isinstance(node.func.value, ast.Name)):
            base = node.func.value.id
            owner, bindings = self.resolve(base, node.func.value)
            if len(bindings) == 1 and bindings[0].kind == 'import' and not bindings[0].conditional:
                binding = bindings[0]
                if binding.imported and not binding.imported.startswith('.'):
                    resolution, candidates, reason = 'candidate', [binding.imported + '.' + attr], 'module_alias_candidate'
                    dynamic = binding.imported == 'importlib' and attr == 'import_module'
            elif bindings:
                reason = 'receiver_shadowed_or_ambiguous'
        return {'scope': scope.qualified_name, 'scope_occurrence': scope.occurrence_key, 'scope_kind': scope.kind,
                'resolution': resolution, 'candidates': candidates, 'binding_reason': reason,
                'dynamic_import': dynamic,
                'binding_confidence': 'candidate_only' if candidates else 'unknown'}
