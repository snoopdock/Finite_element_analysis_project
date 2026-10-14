"""Independent package-level release gate for AE-07 (no source writes)."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile

import yaml

PREFIX='STAGE1_SECTION_UUIDS/'
PROFILE=PREFIX+'validation/profiles/G9.8.yaml'
REQUIRED={
    PROFILE,
    PREFIX+'audit_engine/semantic_audit/ae07/__init__.py',
    PREFIX+'audit_engine/semantic_audit/ae07/__main__.py',
    PREFIX+'audit_engine/semantic_audit/ae07/service.py',
    PREFIX+'audit_engine/semantic_audit/ae07/publication.py',
    PREFIX+'audit_engine/semantic_audit/ae07/sarif.py',
    PREFIX+'audit_engine/semantic_audit/ae07/AE07_METHOD_AND_LIMITATIONS.md',
    PREFIX+'audit_engine/semantic_audit/ae07/README.md',
    PREFIX+'tests/semantic_audit/test_ae07_portfolio.py',
    PREFIX+'tests/semantic_audit/test_ae07_release.py',
    PREFIX+'tools/ae07_release_check.py',
    'README.md','PATCH_MAP.md','LOCAL_VALIDATION_RESULTS.md','SHA256SUMS.txt',
    'VALIDATION_LOGS/AE07_targeted.log','VALIDATION_LOGS/Focused_compatibility.log',
    'VALIDATION_LOGS/Profile_selected_incomplete.log','VALIDATION_LOGS/Full_regression_incomplete.log',
    'VALIDATION_LOGS/Fresh_install_selected.log','VALIDATION_LOGS/Non_AE_regression_incomplete.log',
}


def check(path: Path | str, repo: Path | str) -> dict:
    repository=Path(repo)
    with zipfile.ZipFile(path) as archive:
        infos=archive.infolist()
        names=[i.filename for i in infos if not i.is_dir()]
        if not infos or any(i.is_dir() and ('..' in i.filename or '\\' in i.filename) for i in infos):
            raise ValueError('Unsafe archive directory')
        if len(names)!=len(set(names)) or set(names)!=REQUIRED:
            raise ValueError('Required profile, source, tests, or documentation missing or unexpected member')
        for meta in infos:
            name=meta.filename
            segments=PurePosixPath(name).parts
            if (name.startswith('/') or name.startswith('\\') or '\\' in name or
                    any(s in ('','.','..') for s in segments) or ':' in name or
                    name.endswith(('.pyc','.pyo')) or '__pycache__' in segments or
                    (meta.external_attr>>16)&0o170000 == 0o120000):
                raise ValueError('Unsafe or compiled archive member')
        manifest=archive.read('SHA256SUMS.txt').decode('ascii').splitlines()
        digests={}
        for line in manifest:
            match=re.fullmatch(r'([0-9a-f]{64})  ([^\s]+)',line)
            if not match or match[2] in digests:
                raise ValueError('Invalid or duplicate SHA256SUMS entry')
            digests[match[2]]=match[1]
        if set(digests)!=set(names)-{'SHA256SUMS.txt'}:
            raise ValueError('Checksum manifest does not cover exactly the archive files')
        for name,hash_value in digests.items():
            if hashlib.sha256(archive.read(name)).hexdigest()!=hash_value:
                raise ValueError(f'Archive content checksum mismatch: {name}')
        profile=yaml.safe_load(archive.read(PROFILE))
        if profile['id']!='G9.8' or not profile['regression']['enabled'] or profile['regression']['path']!='tests/':
            raise ValueError('Invalid G9.8 regression profile')
        selected=profile['target_tests']
        if not isinstance(selected,list) or not selected or len(set(selected))!=len(selected):
            raise ValueError('Invalid or duplicate selected test paths')
        if 'tests/semantic_audit/test_ae07_portfolio.py' not in selected or 'tests/semantic_audit/test_ae07_release.py' not in selected:
            raise ValueError('AE-07 tests are not selected')
        for target in selected:
            if not isinstance(target,str) or not target.startswith('tests/') or '..' in PurePosixPath(target).parts:
                raise ValueError('Invalid test target')
            if target not in [member[len(PREFIX):] for member in names if member.startswith(PREFIX)]:
                expected=repository/target
                if not expected.is_file() or expected.is_symlink():
                    raise ValueError(f'Missing validation target: {target}')
        return {'profile':'G9.8','files':len(names), 'selected_tests':len(selected),
                'checksums':'verified','source_branch_only':True}


def main(argv=None):
    p=argparse.ArgumentParser(description='Verify exact packaged AE-07 release bytes')
    p.add_argument('--zip',required=True,type=Path)
    p.add_argument('--repository',required=True,type=Path)
    args=p.parse_args(argv)
    try:
        print(check(args.zip,args.repository))
    except (ValueError,KeyError,OSError,TypeError,zipfile.BadZipFile) as exc:
        print(f'AE-07 release check failed: {exc}',file=sys.stderr)
        return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
