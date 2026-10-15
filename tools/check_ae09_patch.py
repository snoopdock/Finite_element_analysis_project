"""Independently inspect exact AE-09 release ZIP bytes, including G9.10 profile.

Usage: python tools/check_ae09_patch.py /path/to/AE-09.zip
"""
from __future__ import annotations
import hashlib
from pathlib import Path, PurePosixPath
import re
import sys
from zipfile import ZipFile

REQUIRED={
 'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae09/__init__.py',
 'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae09/__main__.py',
 'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae09/investigate.py',
 'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae09/publication.py',
 'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae09/METHOD_AND_LIMITATIONS.md',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/test_ae09_investigation.py',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/test_ae09_release.py',
 'STAGE1_SECTION_UUIDS/tools/check_ae09_patch.py',
 'STAGE1_SECTION_UUIDS/validation/profiles/G9.10.yaml',
 'PATCH_MAP.md','LOCAL_VALIDATION_RESULTS.md','README.md','SHA256SUMS.txt',
}
PROFILE='STAGE1_SECTION_UUIDS/validation/profiles/G9.10.yaml'


def check(path:str|Path, *, repository_root:Path|None=None)->dict:
    p=Path(path)
    with ZipFile(p) as z:
        infos=z.infolist()
        names=[info.filename for info in infos]
        if len(names)!=len(set(names)) or not names or any(info.is_dir() for info in infos):
            raise ValueError('Duplicate or directory members in release archive')
        for info in infos:
            name=info.filename
            pure=PurePosixPath(name)
            if (name.startswith('/') or '\\' in name or ':' in name or
                pure.as_posix()!=name or '..' in pure.parts or
                name.endswith(('.pyc','.pyo','.pyd')) or '__pycache__' in pure.parts or
                ((info.external_attr>>16)&0o170000)==0o120000):
                raise ValueError(f'Unsafe release member: {name}')
            if info.file_size>2_000_000:
                raise ValueError('Unexpectedly large archive member')
            if (not name.startswith('STAGE1_SECTION_UUIDS/') and
                not name.startswith('VALIDATION_LOGS/') and name not in (
                'SHA256SUMS.txt','README.md','PATCH_MAP.md','LOCAL_VALIDATION_RESULTS.md')):
                raise ValueError(f'Unexpected release root member: {name}')
        if not REQUIRED <= set(names):
            raise ValueError(f'Missing essential package members: {sorted(REQUIRED-set(names))}')
        record=z.read('SHA256SUMS.txt').decode('utf-8').splitlines()
        checks={}
        for line in record:
            match=re.fullmatch(r'([a-f0-9]{64})  (.+)',line)
            if not match or match[2] in checks:
                raise ValueError('Malformed or duplicate SHA256 entry')
            checks[match[2]]=match[1]
        files=set(names)-{'SHA256SUMS.txt'}
        if set(checks)!=files:
            raise ValueError('SHA256 manifest does not cover exact ZIP membership')
        for name,digest in checks.items():
            if hashlib.sha256(z.read(name)).hexdigest()!=digest:
                raise ValueError(f'Checksum mismatch: {name}')
        profile=z.read(PROFILE).decode('utf-8')
        if not re.search(r'(?m)^id: G9\.10\s*$',profile):
            raise ValueError('Missing expected G9.10 profile identity')
        tests=[]
        in_targets=False
        for line in profile.splitlines():
            if line.startswith('target_tests:'):
                in_targets=True;continue
            if in_targets and line and not line.startswith('  '):
                in_targets=False
            if in_targets and line.lstrip().startswith('- '):
                rel=line.strip()[2:]
                if not rel.startswith('tests/') or not rel.endswith('.py') or '..' in PurePosixPath(rel).parts:
                    raise ValueError('Invalid target test path')
                tests.append(rel)
        if not tests or len(tests)!=len(set(tests)):
            raise ValueError('Missing or duplicate test targets')
        if 'tests/semantic_audit/test_ae09_investigation.py' not in tests or 'tests/semantic_audit/test_ae09_release.py' not in tests:
            raise ValueError('AE-09 tests absent from actual validation profile')
        for target in tests:
            member='STAGE1_SECTION_UUIDS/'+target
            if member not in names and (repository_root is None or not (repository_root/target).is_file()):
                raise ValueError(f'Invalid profile test target: {target}')
    return {'profile':'G9.10','files':len(names),'selected_test_modules':len(tests),'verified':True}


def main(argv=None)->int:
    import argparse,json
    parser=argparse.ArgumentParser()
    parser.add_argument('archive',type=Path)
    parser.add_argument('--repository-root',type=Path,default=None)
    args=parser.parse_args(argv)
    try:
        print(json.dumps(check(args.archive,repository_root=args.repository_root),sort_keys=True))
        return 0
    except Exception as exc:
        print(f'AE-09 release validation error: {type(exc).__name__}: {exc}',file=sys.stderr)
        return 1

if __name__=='__main__':sys.exit(main())
