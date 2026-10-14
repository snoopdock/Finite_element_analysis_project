"""AE-02.1 deterministic release check for actual patch ZIP bytes.

Fail closed if the required manual G9.3 profile, implementation or tests are
missing, changed without updating SHA256SUMS, or impossible to install safely.
This checker also validates the actual profile selection contract, including
its targeted test paths and the full regression target.
"""
from __future__ import annotations

import argparse
import hashlib
import io
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import zipfile

REQUIRED = frozenset({
    'README.md', 'PATCH_MAP.md', 'LOCAL_VALIDATION_RESULTS.md', 'SHA256SUMS.txt',
    'STAGE1_SECTION_UUIDS/validation/profiles/G9.3.yaml',
    'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae02/impact.py',
    'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae02/service.py',
    'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae02/delta.py',
    'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae02/__main__.py',
    'STAGE1_SECTION_UUIDS/tests/semantic_audit/test_ae021_impact.py',
    'STAGE1_SECTION_UUIDS/tools/check_ae021_patch.py',
})
PROFILE = 'STAGE1_SECTION_UUIDS/validation/profiles/G9.3.yaml'


def check_package(package: Path, repository_root: Path) -> list[str]:
    errors: list[str] = []
    try:
        with zipfile.ZipFile(package) as z:
            infos = z.infolist()
            names = [i.filename for i in infos]
            if len(names) != len(set(names)):
                errors.append('Duplicate ZIP entry name')
            members = set(names)
            for info in infos:
                name = info.filename
                path = PurePosixPath(name)
                mode = (info.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK:
                    errors.append('Symlink archive member: ' + name)
                if (not name or name.startswith('/') or '\\' in name or
                        any(part in ('', '.', '..') for part in path.parts) or
                        name.endswith('/') or ':' in name or '\x00' in name):
                    errors.append('Unsafe ZIP path: ' + name)
                if any(part == '__pycache__' for part in path.parts) or name.endswith(('.pyc', '.pyo')):
                    errors.append('Compiled artifact forbidden: ' + name)
                if name.startswith('MAIN_BRANCH/'):
                    errors.append('Main dispatcher must not be silently modified')
                if name not in ('README.md','PATCH_MAP.md','LOCAL_VALIDATION_RESULTS.md','SHA256SUMS.txt') and not name.startswith('STAGE1_SECTION_UUIDS/'):
                    errors.append('Unknown install destination: ' + name)
                if info.file_size > 5_000_000:
                    errors.append('Unexpected oversized file: ' + name)
            errors.extend('Missing required member: ' + name for name in sorted(REQUIRED - members))
            if 'SHA256SUMS.txt' in members:
                referenced: set[str] = set()
                for line in z.read('SHA256SUMS.txt').decode('utf-8').splitlines():
                    if not line.strip():
                        continue
                    if '  ' not in line:
                        errors.append('Malformed SHA256SUMS record')
                        continue
                    expected, filename = line.split('  ', 1)
                    if not re.fullmatch(r'[0-9a-f]{64}', expected) or filename not in members or filename in referenced:
                        errors.append('Invalid checksum path/duplicate: ' + filename)
                        continue
                    referenced.add(filename)
                    if hashlib.sha256(z.read(filename)).hexdigest() != expected:
                        errors.append('Checksum mismatch: ' + filename)
                if referenced != members - {'SHA256SUMS.txt'}:
                    errors.append('SHA256SUMS coverage incomplete')
            if PROFILE in members:
                try:
                    import yaml
                    entry = yaml.safe_load(io.BytesIO(z.read(PROFILE)))
                    if not isinstance(entry, dict) or entry.get('id') != 'G9.3':
                        errors.append('Profile ID mismatch')
                    paths = entry.get('target_tests') if isinstance(entry, dict) else None
                    if not isinstance(paths, list) or len(paths) < 4 or len(set(paths)) != len(paths):
                        errors.append('Malformed or duplicate targeted tests')
                    else:
                        if 'tests/semantic_audit/test_ae021_impact.py' not in paths:
                            errors.append('G9.3 must execute new impact tests')
                        for p in paths:
                            if not isinstance(p, str) or not p.startswith('tests/') or '..' in PurePosixPath(p).parts:
                                errors.append('Unsafe targeted test path: ' + repr(p))
                            elif (f'STAGE1_SECTION_UUIDS/{p}' not in members and
                                  not (repository_root / p).is_file()):
                                errors.append('Target test absent after install: ' + p)
                    if entry.get('regression') != {'enabled': True, 'path': 'tests/'}:
                        errors.append('Full regression profile contract missing')
                except Exception as exc:
                    errors.append('Profile unreadable: ' + type(exc).__name__ + ': ' + str(exc))
    except (OSError, zipfile.BadZipFile, ValueError) as exc:
        errors.append('Patch archive unreadable: ' + str(exc))
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Verify the AE-02.1 G9.3 release package')
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--repository-root', type=Path, required=True)
    args = parser.parse_args(argv)
    issues = check_package(args.package, args.repository_root)
    if issues:
        for issue in issues:
            print('ERROR:', issue, file=sys.stderr)
        return 1
    print('PASS: G9.3 present; target tests, checksums, archive safety and regression contract validated')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
