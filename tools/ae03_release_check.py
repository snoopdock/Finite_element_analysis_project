"""AE-03 package release gate: run before distributing and after installation.

No GitHub action is created or triggered. Pure-stdlib inspection of exact ZIP
bytes; intentionally fails closed on missing profile or unscoped targets.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from zipfile import ZipFile

PROFILE = 'STAGE1_SECTION_UUIDS/validation/profiles/G9.4.yaml'
PREFIX = 'STAGE1_SECTION_UUIDS/'
REQUIRED = {
    PROFILE,
    PREFIX + 'audit_engine/semantic_audit/ae03/__init__.py',
    PREFIX + 'audit_engine/semantic_audit/ae03/__main__.py',
    PREFIX + 'audit_engine/semantic_audit/ae03/source.py',
    PREFIX + 'audit_engine/semantic_audit/ae03/runner.py',
    PREFIX + 'audit_engine/semantic_audit/ae03/impact.py',
    PREFIX + 'tests/semantic_audit/test_ae03_mutation.py',
    PREFIX + 'tests/semantic_audit/test_ae03_release.py',
}


def _profile_paths(data: bytes) -> list[str]:
    # Exact subset used in the project's G9.1-G9.3 YAML profiles.
    try:
        text = data.decode('utf-8')
    except UnicodeError as exc:
        raise ValueError('Validation profile not UTF-8') from exc
    if not re.search(r'^id:\s*G9\.4\s*$', text, re.M):
        raise ValueError('G9.4 profile ID mismatch')
    if not re.search(r'^regression:\s*\n\s*enabled:\s*true', text, re.M):
        raise ValueError('Profile regression is not enabled')
    match = re.search(r'^target_tests:\s*\n((?:\s+-\s+[^\n]+\n)+)', text, re.M)
    if match is None:
        raise ValueError('G9.4 lacks target_tests')
    paths = [line.strip().removeprefix('-').strip() for line in match.group(1).splitlines()]
    if len(paths) != len(set(paths)) or any(not p.startswith('tests/') or not p.endswith('.py')
                                           or '..' in PurePosixPath(p).parts for p in paths):
        raise ValueError('Unsafe/duplicate profile test target')
    if 'tests/semantic_audit/test_ae03_mutation.py' not in paths or 'tests/semantic_audit/test_ae03_release.py' not in paths:
        raise ValueError('AE-03 adversarial and release tests must both be targeted')
    return paths


def check(package: Path, repository: Path) -> dict:
    package, repository = Path(package), Path(repository)
    if not repository.is_dir():
        raise ValueError('A baseline repository checkout is required')
    with ZipFile(package) as z:
        info = z.infolist()
        names = [i.filename for i in info]
        if len(names) != len(set(names)):
            raise ValueError('Duplicate ZIP members')
        for member in info:
            n = member.filename
            p = PurePosixPath(n)
            if (not n or n.startswith('/') or '\\' in n or p.is_absolute() or
                '..' in p.parts or '.' in p.parts or n != str(p) or member.is_dir()):
                raise ValueError(f'Unsafe archive member: {n}')
            if stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError('ZIP symlink member is forbidden')
            if n.endswith(('.pyc', '.pyo')) or '__pycache__' in p.parts:
                raise ValueError('Compiled files are forbidden')
        if not REQUIRED.issubset(names):
            raise ValueError('Missing G9.4 profile or essential implementation/tests: '
                             + repr(sorted(REQUIRED - set(names))))
        sums = z.read('SHA256SUMS.txt').decode('ascii').splitlines()
        entries = {}
        for line in sums:
            parts = line.split('  ', 1)
            if len(parts) != 2 or not re.fullmatch(r'[a-f0-9]{64}', parts[0]) or parts[1] in entries:
                raise ValueError('Invalid checksum manifest entry')
            entries[parts[1]] = parts[0]
        if set(entries) != set(names) - {'SHA256SUMS.txt'}:
            raise ValueError('Checksum file set disagrees with ZIP membership')
        for name, expected in entries.items():
            if hashlib.sha256(z.read(name)).hexdigest() != expected:
                raise ValueError('Incorrect package checksum for ' + name)
        targets = _profile_paths(z.read(PROFILE))
        for path in targets:
            if PREFIX + path not in names and not (repository / path).is_file():
                raise ValueError('G9.4 profile references absent test: ' + path)
        if any(n.startswith('MAIN_BRANCH/') and n != 'MAIN_BRANCH/NO_CHANGES.md' for n in names):
            raise ValueError('Unreviewed central dispatcher modification')
    return {'profile': 'G9.4', 'targets': targets, 'files': len(names), 'checksum_status': 'passed'}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('package', type=Path)
    p.add_argument('--repository', required=True, type=Path)
    args = p.parse_args(argv)
    try:
        print(json.dumps(check(args.package, args.repository), sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, UnicodeDecodeError) as exc:
        print(f'AE-03 release FAIL: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
