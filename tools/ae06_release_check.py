"""AE-06 mandatory release gate: validate the *actual ZIP* before upload.

Cross-check target profiles with the candidate checkout, confirm strict file
membership and independent SHA-256 hashes, reject symlinks/traversal, and
ensure parser-valid Python payloads. Does not replace runtime tests.
"""
from __future__ import annotations
import ast
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import zipfile
import yaml

PREFIX = 'STAGE1_SECTION_UUIDS/'
PROFILE = PREFIX + 'validation/profiles/G9.7.yaml'
REQUIRED = frozenset(PREFIX + name for name in [
    'audit_engine/semantic_audit/ae06/__init__.py',
    'audit_engine/semantic_audit/ae06/__main__.py',
    'audit_engine/semantic_audit/ae06/service.py',
    'audit_engine/semantic_audit/ae06/publication.py',
    'audit_engine/semantic_audit/ae06/AE06_METHOD_AND_LIMITATIONS.md',
    'tests/semantic_audit/test_ae06_remediation.py',
    'tests/semantic_audit/test_ae06_release.py',
    'tools/ae06_release_check.py',
    'validation/profiles/G9.7.yaml'])
DOCUMENTS = frozenset({'README.md', 'PATCH_MAP.md', 'LOCAL_VALIDATION_RESULTS.md',
                       'VALIDATION_LOGS/full_repository_pytest.log',
                       'VALIDATION_LOGS/G9_7_selected_pytest.log'})


def _profile_paths(data: bytes) -> tuple[str,...]:
    try:
        contents = yaml.safe_load(data)
    except yaml.YAMLError as error:
        raise ValueError('Malformed G9.7 profile YAML') from error
    if not isinstance(contents,dict) or contents.get('id')!='G9.7':
        raise ValueError('G9.7 profile ID mismatch')
    targets=contents.get('target_tests')
    if not isinstance(targets,list) or len(targets)<8 or len(set(targets))!=len(targets):
        raise ValueError('Missing, duplicated or inadequate G9.7 targeted test set')
    if contents.get('regression') != {'enabled':True,'path':'tests/'}:
        raise ValueError('G9.7 regression contract mismatch')
    for target in targets:
        if not isinstance(target,str) or not target.startswith('tests/') or not target.endswith('.py'):
            raise ValueError('Unsafe targeted test path')
        parts=PurePosixPath(target).parts
        if '..' in parts or '.' in parts or str(PurePosixPath(target))!=target:
            raise ValueError('Unsafe targeted test path')
    if not {'tests/semantic_audit/test_ae06_remediation.py', 'tests/semantic_audit/test_ae06_release.py'} <= set(targets):
        raise ValueError('G9.7 lacks AE-06 test targets')
    return tuple(targets)


def check(archive: Path | str, checkout: Path | str) -> dict:
    checkout=Path(checkout)
    archive=Path(archive)
    with zipfile.ZipFile(archive) as z:
        infos=z.infolist()
        names=[i.filename for i in infos]
        if len(names)!=len(set(names)):
            raise ValueError('Duplicate ZIP entry names')
        if len(names)>100 or sum(i.file_size for i in infos)>10_000_000:
            raise ValueError('Release archive exceeds reviewed size budget')
        for entry in infos:
            name=entry.filename
            path=PurePosixPath(name)
            if (name.endswith('/') or name.startswith('/') or '\\' in name or '\x00' in name or
                any(part in ('.','..') for part in path.parts) or str(path)!=name):
                raise ValueError('Unsafe ZIP member path')
            if stat.S_IFMT(entry.external_attr >> 16)==stat.S_IFLNK:
                raise ValueError('ZIP symlink entry forbidden')
            if '__pycache__' in path.parts or name.endswith(('.pyc','.pyo')):
                raise ValueError('Compiled Python payload forbidden')
        names_set=set(names)
        expected=REQUIRED | DOCUMENTS | {'SHA256SUMS.txt'}
        if names_set != expected:
            raise ValueError(f'Missing/unexpected release files: missing={sorted(expected-names_set)}, extra={sorted(names_set-expected)}')
        listed=z.read('SHA256SUMS.txt').decode('ascii').splitlines()
        actual={}
        for line in listed:
            parts=line.split('  ',1)
            if len(parts)!=2 or len(parts[0])!=64 or not all(c in '0123456789abcdef' for c in parts[0]):
                raise ValueError('Invalid SHA256SUMS entry')
            digest,name=parts
            if name in actual:
                raise ValueError('Duplicate checksum member')
            actual[name]=digest
        if set(actual)!=names_set-{'SHA256SUMS.txt'}:
            raise ValueError('SHA256SUMS member coverage mismatch')
        if listed!=[f'{actual[n]}  {n}' for n in sorted(actual)]:
            raise ValueError('SHA256SUMS is not deterministically ordered')
        for name in actual:
            if hashlib.sha256(z.read(name)).hexdigest()!=actual[name]:
                raise ValueError(f'ZIP member checksum mismatch: {name}')
        targets=_profile_paths(z.read(PROFILE))
        for path in targets:
            archive_target=PREFIX+path
            if archive_target in names_set:
                if z.read(archive_target)!=(checkout/path).read_bytes():
                    raise ValueError(f'Packaged test differs from candidate checkout: {path}')
            elif not (checkout/path).is_file() or (checkout/path).is_symlink():
                raise ValueError(f'Missing/unsafe selected test target: {path}')
        for name in REQUIRED:
            relative=name[len(PREFIX):]
            if (checkout/relative).is_symlink() or z.read(name)!=(checkout/relative).read_bytes():
                raise ValueError(f'Packaged implementation differs from checkout: {relative}')
            if name.endswith('.py'):
                ast.parse(z.read(name),filename=name)
    return {'profile':'G9.7','status':'passed','checksum_status':'passed',
            'file_count':len(names),'target_tests':len(targets)}


if __name__=='__main__':
    if len(sys.argv)!=3:
        raise SystemExit('Usage: python tools/ae06_release_check.py <zip> <candidate-checkout>')
    print(check(sys.argv[1],sys.argv[2]))
