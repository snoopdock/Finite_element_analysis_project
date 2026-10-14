"""Exact-byte Python inventory, static source facts and conservative import resolution.

This analysis intentionally makes no claim of full Python binding or dispatch soundness.
"""
from __future__ import annotations

import ast
import hashlib
import os
from pathlib import Path, PurePosixPath
from typing import Any

EXCLUDE_DIRS = frozenset({'.git', '__pycache__', '.venv', 'venv', '.tox', '.mypy_cache', '.pytest_cache'})
SCHEMA = 'ae01/source_manifest/v1'


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inventory(root: Path, *, excludes: tuple[str, ...] = (), output: Path | None = None) -> tuple[dict, dict[str, bytes]]:
    root = Path(root).absolute()
    if not root.is_dir() or root.is_symlink():
        raise ValueError('Source root must be an existing non-symlink directory')
    banned = set(EXCLUDE_DIRS) | set(excludes)
    if any(not name or '/' in name or '\\' in name or name in ('.', '..') for name in banned):
        raise ValueError('Exclusions must be exact directory names')
    records: list[dict[str, Any]] = []
    sources: dict[str, bytes] = {}
    output_abs = output.absolute() if output is not None else None
    for current, dirs, files in os.walk(root, followlinks=False):
        parent = Path(current)
        dirs.sort()
        files.sort()
        for name in list(dirs):
            path = parent / name
            rel = path.relative_to(root).as_posix()
            reason = ('excluded_directory' if name in banned else
                      'output_directory' if output_abs is not None and path == output_abs else
                      'symlink_directory' if path.is_symlink() else None)
            if reason:
                dirs.remove(name)
                records.append({'path': rel + '/', 'status': 'excluded', 'reason': reason})
        for name in files:
            if not name.endswith('.py'):
                continue
            path = parent / name
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                records.append({'path': rel, 'status': 'excluded', 'reason': 'symlink_file'})
                continue
            if not path.is_file():
                records.append({'path': rel, 'status': 'error', 'reason': 'not_regular_file'})
                continue
            try:
                # O_NOFOLLOW rejects a last-moment file symlink substitution.
                fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
                try:
                    before = os.fstat(fd)
                    if not before.st_mode & 0o444:
                        raise PermissionError('no read permission bits')
                    with os.fdopen(fd, 'rb', closefd=False) as stream:
                        raw = stream.read()
                    after = os.fstat(fd)
                    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                        raise OSError('source changed during reading')
                    if path.is_symlink() or path.stat().st_ino != before.st_ino or path.stat().st_dev != before.st_dev:
                        raise OSError('source replaced during reading')
                finally:
                    os.close(fd)
                # Python's encoding rules allow BOM/PEP 263, not just UTF-8.
                import io, tokenize
                encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
                decoded = raw.decode(encoding)
                ast.parse(decoded, filename=rel)
                sources[rel] = raw
                records.append({'path': rel, 'status': 'included', 'sha256': digest(raw), 'bytes': len(raw), 'encoding': encoding})
            except (OSError, UnicodeError, SyntaxError, LookupError, ValueError, PermissionError) as exc:
                records.append({'path': rel, 'status': 'error', 'reason': type(exc).__name__, 'detail': str(exc)[:300]})
    records.sort(key=lambda r: r['path'])
    summary = {key: sum(r['status'] == key for r in records) for key in ('included', 'excluded', 'error')}
    manifest = {'schema': SCHEMA, 'source_root': '.', 'exclusions': sorted(banned), 'files': records, 'summary': summary}
    return manifest, sources


def module_name(path: str) -> str:
    parts = list(PurePosixPath(path).parts)
    if parts[-1] == '__init__.py':
        return '.'.join(parts[:-1]) or '__root__'
    return '.'.join(parts)[:-3]


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return (_call_name(node.value) + '.' + node.attr).lstrip('.')
    return '<dynamic>'


class _Facts(ast.NodeVisitor):
    def __init__(self, path: str, module: str, package: str):
        self.path, self.module, self.package = path, module, package
        self.imports: list[dict] = []
        self.calls: list[dict] = []
        self.functions: list[dict] = []
        self.context: list[str] = []
        self.aliases: dict[str, str] = {}
        self.order = 0

    def _new(self, node: ast.AST, kind: str, **values) -> dict:
        self.order += 1
        return {'id': f'{kind}:{self.path}:{node.lineno}:{node.col_offset}:{self.order}',
                'file': self.path, 'line': node.lineno, 'column': node.col_offset,
                'end_line': getattr(node, 'end_lineno', node.lineno),
                'end_column': getattr(node, 'end_col_offset', node.col_offset),
                'context': list(self.context), **values}

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(self._new(node, 'import', module=alias.name, level=0,
                                          symbol=None, alias=alias.asname, form='import'))
            self.aliases[alias.asname or alias.name.split('.')[0]] = alias.name if alias.asname else alias.name.split('.')[0]

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self.imports.append(self._new(node, 'import', module=node.module or '', level=node.level,
                                          symbol=alias.name, alias=alias.asname, form='from'))
            self.aliases[alias.asname or alias.name] = ('.' * node.level) + (node.module + '.' if node.module else '') + alias.name

    def visit_If(self, node: ast.If) -> None:
        cond = _call_name(node.test)
        type_check = cond in ('TYPE_CHECKING', 'typing.TYPE_CHECKING') or cond.endswith('.TYPE_CHECKING')
        self.context.append('type_checking' if type_check else 'conditional')
        self.visit(node.test)
        for child in node.body: self.visit(child)
        self.context.pop()
        if node.orelse:
            self.context.append('conditional_else')
            for child in node.orelse: self.visit(child)
            self.context.pop()

    def visit_For(self, node: ast.For | ast.AsyncFor) -> None:
        self.visit(node.iter)
        self.context.append('conditional_loop')
        for child in node.body + node.orelse:
            self.visit(child)
        self.context.pop()

    visit_AsyncFor = visit_For

    def visit_While(self, node: ast.While) -> None:
        self.visit(node.test)
        self.context.append('conditional_loop')
        for child in node.body + node.orelse:
            self.visit(child)
        self.context.pop()

    def visit_Match(self, node: ast.Match) -> None:
        self.visit(node.subject)
        self.context.append('conditional_match')
        for case in node.cases:
            self.visit(case)
        self.context.pop()

    def visit_Try(self, node: ast.Try) -> None:
        self.context.append('try')
        for child in node.body: self.visit(child)
        self.context.pop()
        for child in node.handlers + node.orelse + node.finalbody:
            self.context.append('conditional')
            self.visit(child)
            self.context.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.functions.append(self._new(node, 'function', name=node.name))
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call) -> None:
        spelling = _call_name(node.func)
        dynamic = spelling in ('__import__', 'importlib.import_module') or (
            spelling.endswith('.import_module') and self.aliases.get(spelling.split('.')[0]) == 'importlib') or (
            self.aliases.get(spelling) == 'importlib.import_module')
        literal = (node.args[0].value if dynamic and node.args and
                   isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str) else None)
        self.calls.append(self._new(node, 'call', spelling=spelling, receiver=spelling.rpartition('.')[0],
                                    resolution='unresolved', candidates=[], dynamic_import=dynamic,
                                    literal_target=literal))
        if spelling in ('exec', 'eval'):
            self.imports.append(self._new(node, 'import', module='', level=0, symbol=None,
                                          alias=None, form='dynamic_unresolved'))
        if dynamic:
            self.imports.append(self._new(node, 'import', module=literal or '', level=0,
                                          symbol=None, alias=None, form='dynamic_literal' if literal else 'dynamic_unresolved'))
        self.generic_visit(node)


def extract(sources: dict[str, bytes], manifest: dict, classifications: dict[str, str]) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    path_by_module: dict[str, list[str]] = {}
    for path in sorted(sources):
        path_by_module.setdefault(module_name(path), []).append(path)
    imports, calls, functions, issues = [], [], [], []
    for module, paths in sorted(path_by_module.items()):
        if len(paths) > 1:
            issues.append({'kind': 'ambiguous_module_identity', 'module': module, 'paths': paths})
    for path in sorted(sources):
        module = module_name(path)
        package = module if path.endswith('/__init__.py') else module.rpartition('.')[0]
        raw = sources[path]
        encoding = next(r['encoding'] for r in manifest['files'] if r['path'] == path)
        parsed = ast.parse(raw.decode(encoding), filename=path)
        facts = _Facts(path, module, package)
        facts.visit(parsed)
        functions.extend(facts.functions)
        for imp in facts.imports:
            if imp['symbol'] == '*':
                status, target, candidates, reason = 'unresolved', None, [], 'star_import_runtime_bindings'
            elif imp['form'] == 'dynamic_unresolved':
                status, target, candidates, reason = 'unresolved', None, [], 'dynamic_expression'
            else:
                prefix = package.split('.') if package and package != '__root__' else []
                if imp['level']:
                    if imp['level'] > len(prefix) + 1:
                        status, target, candidates, reason = 'unresolved', None, [], 'relative_beyond_top'
                        imp.update(status=status, target=target, candidates=candidates, reason=reason)
                        imports.append(imp); issues.append({'kind': 'unresolved_import', 'occurrence_id': imp['id'], 'reason': reason}); continue
                    prefix = prefix[:len(prefix) - imp['level'] + 1]
                    base = '.'.join(prefix + ([imp['module']] if imp['module'] else []))
                else:
                    base = imp['module']
                child = base + '.' + imp['symbol'] if imp['symbol'] and imp['symbol'] != '*' else None
                if child in path_by_module:
                    candidate = child
                else:
                    candidate = base
                targets = path_by_module.get(candidate, [])
                if len(targets) > 1:
                    status, target, candidates, reason = 'ambiguous', None, targets, 'duplicate_module_identity'
                elif len(targets) == 1:
                    status, target, candidates, reason = 'internal', candidate, targets, None
                elif imp['level']:
                    status, target, candidates, reason = 'unresolved', None, [], 'unresolved_relative'
                else:
                    status, target, candidates, reason = 'external', candidate, [], None
            imp.update(status=status, target=target, candidates=candidates, reason=reason)
            imports.append(imp)
            if status in ('unresolved', 'ambiguous'):
                issues.append({'kind': 'unresolved_import', 'occurrence_id': imp['id'], 'reason': reason})
        for call in facts.calls:
            # Conservative binding: Python runtime mutation and shadowing prevent claiming sound exact callees.
            if call['spelling'] in {f['name'] for f in facts.functions}:
                call['resolution'] = 'candidate'
                call['candidates'] = [module + '.' + call['spelling']]
            elif call['receiver'] in facts.aliases:
                call['resolution'] = 'candidate'
                call['candidates'] = [facts.aliases[call['receiver']] + '.' + call['spelling'].split('.')[-1]]
            calls.append(call)
    return imports, calls, functions, issues
