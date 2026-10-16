"""Manual, read-only, bounded semantic contract analysis and exact report replay.

Usage: python -m audit_engine.semantic_audit.ae25 analyze --contract CONTRACT.json --evidence-dir evidence/
       python -m audit_engine.semantic_audit.ae25 verify --contract CONTRACT.json --evidence-dir evidence/ --report REPORT.json

Output is canonical JSON on stdout. No source execution, external network, or graph mutations.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat

from audit_engine.semantic_audit.ae24.contracts import canonical, ContractError, MAX_BYTES, MAX_SOURCE_BYTES
from .reasoner import analyze, verify_report

NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$')


def _read_regular(path: Path, limit: int):
    path = Path(path)
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ContractError('Symlink evidence path forbidden')
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ContractError('Evidence input must be a bounded regular file')
        data = os.read(fd, limit + 1)
        if len(data) != info.st_size:
            raise ContractError('Evidence file was changed during read')
        return data
    finally:
        os.close(fd)


def _document(path: Path):
    data = _read_regular(path, MAX_BYTES)
    try:
        obj = json.loads(data)
    except (ValueError, UnicodeError) as exc:
        raise ContractError('Malformed JSON evidence') from exc
    if canonical(obj) != data or not isinstance(obj, dict):
        raise ContractError('Expected canonical JSON object with final newline')
    return obj


def load_inputs(contract_path: Path, evidence_directory: Path):
    doc = _document(contract_path)
    directory = Path(evidence_directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ContractError('Evidence root must be a real directory')
    sources = doc.get('sources')
    if not isinstance(sources, list):
        raise ContractError('Missing sources list')
    payload = {}
    for row in sources:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str):
            raise ContractError('Invalid source name')
        sid = row['id']
        if not NAME.fullmatch(sid) or sid in {'.', '..'}:
            raise ContractError('Source names must be safe flat filenames')
        if sid in payload:
            raise ContractError('Duplicate source identity')
        payload[sid] = _read_regular(directory / sid, MAX_SOURCE_BYTES)
    return doc, payload


def main(argv=None):
    parser = argparse.ArgumentParser(description='AE-25 bounded language-agnostic structural reasoning')
    parser.add_argument('action', choices=['analyze', 'verify'])
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--evidence-dir', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(argv)
    doc, evidence = load_inputs(args.contract, args.evidence_dir)
    if args.action == 'analyze':
        if args.report is not None:
            parser.error('The analyze command does not accept --report')
        result = analyze(doc, evidence)
    else:
        if args.report is None:
            parser.error('Verification requires --report')
        result = verify_report(doc, evidence, _document(args.report))
    print(canonical(result).decode('utf-8'), end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
