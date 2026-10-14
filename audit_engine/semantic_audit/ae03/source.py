"""AE-03: conservative, occurrence-addressable mutation discovery.

Only a small declared operator family is supported. A selected operator must
have precisely one tokenizer witness between the AST's two operands. This is
NOT arbitrary-Python semantic analysis and never asserts mutant equivalence.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
import io
from pathlib import Path, PurePosixPath
import tokenize
from typing import Iterable

from audit_engine.semantic_audit.ae01.publication import canonical, sha, _no_symlink_components

OPERATORS = {ast.Eq: ('==', '!='), ast.NotEq: ('!=', '=='),
             ast.Lt: ('<', '>='), ast.LtE: ('<=', '>'),
             ast.Gt: ('>', '<='), ast.GtE: ('>=', '<')}
EXCLUDED_DIRS = frozenset({'.git', '.venv', 'venv', '__pycache__', '.pytest_cache',
                            '.mypy_cache', 'build', 'dist', 'node_modules'})


def checked_relative(path: str, *, suffix: str = '.py') -> str:
    if not isinstance(path, str) or not path or '\\' in path or '\x00' in path:
        raise ValueError('Unsafe relative path')
    p = PurePosixPath(path)
    if (p.is_absolute() or '..' in p.parts or '.' in p.parts or
            any(part in EXCLUDED_DIRS for part in p.parts) or
            str(p) != path or not path.endswith(suffix)):
        raise ValueError(f'Unsafe or invalid path: {path}')
    return path


def safe_file(root: Path, relpath: str) -> Path:
    checked_relative(relpath)
    root = Path(root).absolute()
    _no_symlink_components(root)
    result = root / relpath
    _no_symlink_components(result)
    if not result.is_file():
        raise ValueError(f'Missing required Python file: {relpath}')
    return result


@dataclass(frozen=True)
class Mutation:
    mutation_id: str
    path: str
    source_sha256: str
    line: int
    column: int
    original: str
    replacement: str
    mutated_sha256: str
    kind: str = 'comparison_operator'

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _utf8_char_column(line: str, byte_column: int) -> int:
    """AST column values are UTF-8 byte offsets; tokenize uses codepoints."""
    raw = line.encode('utf-8')
    return len(raw[:byte_column].decode('utf-8'))


def _discover(path: str, raw: bytes) -> list[tuple[Mutation, bytes]]:
    # Declaring this narrow source-encoding contract prevents incorrect
    # locations in files using legacy PEP 263 encodings.
    if raw.startswith(b'\xef\xbb\xbf'):
        raise ValueError('UTF-8 BOM is not supported by AE-03 mutation v1')
    text = raw.decode('utf-8', errors='strict')
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text, filename=path)
    tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    source_hash = sha(raw)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    result = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1 and
                type(node.ops[0]) in OPERATORS):
            continue
        left, right = node.left, node.comparators[0]
        if any(not hasattr(n, attr) for n in (left, right) for attr in ('lineno', 'col_offset', 'end_lineno', 'end_col_offset')):
            continue
        op, repl = OPERATORS[type(node.ops[0])]
        left_end = (left.end_lineno, _utf8_char_column(lines[left.end_lineno-1], left.end_col_offset))
        right_start = (right.lineno, _utf8_char_column(lines[right.lineno-1], right.col_offset))
        positions = [t.start for t in tokens if t.type == tokenize.OP and t.string == op and
                     left_end <= t.start < right_start]
        if len(positions) != 1:  # uncertain syntax: decline rather than guess
            continue
        line, column = positions[0]
        offset = offsets[line - 1] + column
        if text[offset:offset+len(op)] != op:
            raise ValueError('Token-location disagreement')
        mutant_text = text[:offset] + repl + text[offset+len(op):]
        mutant_raw = mutant_text.encode('utf-8')
        # Some replacements can create syntactically invalid mutants. Those
        # are reported separately at execution, never counted as killed.
        identifier = sha(canonical({'source_sha256': source_hash, 'file': path,
                                    'line': line, 'column': column,
                                    'original': op, 'replacement': repl}))
        result.append((Mutation('ae03-' + identifier[:32], path, source_hash, line,
                                column, op, repl, sha(mutant_raw)), mutant_raw))
    result.sort(key=lambda x: (x[0].line, x[0].column, x[0].mutation_id))
    if len({m.mutation_id for m, _ in result}) != len(result):
        raise ValueError('Duplicate mutation occurrence identity')
    return result


def discover(root: Path, files: Iterable[str]) -> list[tuple[Mutation, bytes]]:
    """Discover every supported site, sorted by exact repository-relative path."""
    checked = sorted(set(checked_relative(str(path)) for path in files))
    if not checked:
        raise ValueError('An explicit, nonempty source scope is required')
    return [site for rel in checked for site in _discover(rel, safe_file(root, rel).read_bytes())]


def verify_mutation(root: Path, mutation: Mutation) -> bytes:
    """Independent re-derivation from current source bytes and tokenizer/AST."""
    path = safe_file(root, mutation.path)
    raw = path.read_bytes()
    if sha(raw) != mutation.source_sha256:
        raise ValueError('Mutation source has changed since discovery')
    matches = [altered for item, altered in _discover(mutation.path, raw) if item == mutation]
    if len(matches) != 1 or sha(matches[0]) != mutation.mutated_sha256:
        raise ValueError('Mutation witness cannot be independently reproduced')
    return matches[0]
