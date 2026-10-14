"""Fail-closed pre-release checker for manual-dispatch validation patch ZIPs.

Usage:
 python tools/check_validation_patch.py --package PATCH.zip --repository-root . --profile G9.2

Checks the *actual packaged bytes* and the post-install target file paths.
This prevents the original AE-02 missing-profile failure from recurring.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile


def check(package: Path, repository_root: Path, profile: str) -> list[str]:
    errors: list[str] = []
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9.]*', profile):
        return ['Unsafe validation profile identifier']
    try:
        with zipfile.ZipFile(package) as archive:
            filenames = archive.namelist()
            names = set(filenames)
            if len(filenames) != len(names):
                errors.append('Duplicate member in patch ZIP')
            for name in filenames:
                parts = PurePosixPath(name).parts
                if (not name or name.startswith('/') or '\\' in name or
                    '..' in parts or '.' in parts or name.endswith('/') or
                    any(part.startswith('.') and part not in ('.github',) for part in parts)):
                    errors.append(f'Unsafe archive path: {name}')
                if name.endswith(('.pyc', '.pyo')) or '__pycache__' in parts:
                    errors.append(f'Compiled Python artifact forbidden: {name}')
                if name.startswith('MAIN_BRANCH/'):
                    errors.append('Patch must not silently modify main validation dispatcher')
            required = {
                'README.md', 'PATCH_MAP.md', 'LOCAL_VALIDATION_RESULTS.md',
                'SHA256SUMS.txt', f'STAGE1_SECTION_UUIDS/validation/profiles/{profile}.yaml',
                'STAGE1_SECTION_UUIDS/tests/semantic_audit/test_ae02_evolution.py',
            }
            for missing in sorted(required - names):
                errors.append(f'Required patch member missing: {missing}')
            if 'SHA256SUMS.txt' in names:
                seen = set()
                for line in archive.read('SHA256SUMS.txt').decode('utf-8').splitlines():
                    if not line.strip():
                        continue
                    if '  ' not in line:
                        errors.append('Malformed SHA256SUMS entry')
                        continue
                    expected, name = line.split('  ', 1)
                    if not re.fullmatch(r'[0-9a-f]{64}', expected) or name not in names or name in seen:
                        errors.append(f'Invalid checksum reference: {name}')
                        continue
                    seen.add(name)
                    if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                        errors.append(f'Patch member checksum mismatch: {name}')
                if seen != names - {'SHA256SUMS.txt'}:
                    errors.append('SHA256SUMS member coverage incomplete')
            target = f'STAGE1_SECTION_UUIDS/validation/profiles/{profile}.yaml'
            if target in names:
                try:
                    import yaml
                    document = yaml.safe_load(archive.read(target))
                    if document.get('id') != profile:
                        errors.append('Profile YAML id disagrees with dispatcher input')
                    paths = document.get('target_tests')
                    if not isinstance(paths, list) or len(paths) < 2 or len(paths) != len(set(paths)):
                        errors.append('Missing/duplicate targeted tests')
                    else:
                        for path in paths:
                            if not isinstance(path, str) or not path.startswith('tests/') or '..' in PurePosixPath(path).parts:
                                errors.append(f'Invalid targeted test path: {path}')
                            elif not (f'STAGE1_SECTION_UUIDS/{path}' in names or (repository_root/path).is_file()):
                                errors.append(f'Targeted test does not exist after install: {path}')
                    if document.get('regression') != {'enabled': True, 'path': 'tests/'}:
                        errors.append('Full regression target is not enabled')
                except Exception as exc:
                    errors.append(f'Cannot parse validation profile: {type(exc).__name__}: {exc}')
    except (OSError, zipfile.BadZipFile) as exc:
        return [f'Cannot read patch ZIP: {exc}']
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Verify patch/profile completeness before manual GitHub install')
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--repository-root', type=Path, required=True)
    parser.add_argument('--profile', default='G9.2')
    args = parser.parse_args(argv)
    problems = check(args.package, args.repository_root, args.profile)
    if problems:
        for p in problems:
            print('ERROR:', p, file=sys.stderr)
        return 1
    print(f'PASS: {args.profile} package members, YAML, targets, checksums and regression contract')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
