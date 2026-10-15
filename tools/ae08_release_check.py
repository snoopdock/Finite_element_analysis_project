"""Fail-closed check of exact AE-08 patch ZIP, profile and checksums."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile

import yaml

PREFIX='STAGE1_SECTION_UUIDS/'
PROFILE=PREFIX+'validation/profiles/G9.9.yaml'
SOURCES=[
 'audit_engine/semantic_audit/ae08/__init__.py',
 'audit_engine/semantic_audit/ae08/__main__.py',
 'audit_engine/semantic_audit/ae08/benchmark.py',
 'audit_engine/semantic_audit/ae08/README.md',
 'audit_engine/semantic_audit/ae08/AE08_EVALUATION_DESIGN.md',
 'tests/semantic_audit/test_ae08_benchmark.py',
 'tests/semantic_audit/test_ae08_release.py',
 'tools/ae08_release_check.py',
 'validation/profiles/G9.9.yaml',
]
FIXTURES=[
 'tests/fixtures/ae08_gold/'+name for name in (
     'gold.json','app.py','stable.py','experimental.py','control.py',
     'dynamic.py','typing_case.py','duplicate.py','plain.py',
     'pkg/__init__.py','pkg/feature.py','pkg/helper.py')
]+[
 'tests/fixtures/ae08_permitted/'+name for name in ('gold.json','prod.py','stable.py')
]
REQUIRED=({PREFIX+p for p in SOURCES+FIXTURES} |
          {'README.md','PATCH_MAP.md','LOCAL_VALIDATION_RESULTS.md','SHA256SUMS.txt',
           'VALIDATION_LOGS/AE08_targeted.txt','VALIDATION_LOGS/AE08_repository_survey.json',
           'VALIDATION_LOGS/AE08_corpus_score.json','VALIDATION_LOGS/AE08_permitted_score.json',
           'VALIDATION_LOGS/AE08_selected.txt','VALIDATION_LOGS/AE08_full_regression.txt',
           'VALIDATION_LOGS/AE08_fresh_install.txt'})


def check(path: Path | str, repository: Path | str) -> dict:
    repo=Path(repository)
    with zipfile.ZipFile(path) as z:
        members=z.infolist()
        names=[i.filename for i in members]
        if set(names)!=REQUIRED or len(names)!=len(REQUIRED):
            raise ValueError('Required member or validation profile missing, duplicate or unapproved file')
        for member in members:
            name=member.filename
            parts=PurePosixPath(name).parts
            if (member.is_dir() or name.startswith(('/', '\\')) or '\\' in name or
                    ':' in name or any(part in ('', '.', '..','__pycache__') for part in parts) or
                    name.endswith(('.pyc','.pyo')) or (member.external_attr>>16)&0o170000==0o120000):
                raise ValueError('Unsafe or compiled archive member')
        checks=z.read('SHA256SUMS.txt').decode('ascii').splitlines()
        digests={}
        for line in checks:
            m=re.fullmatch(r'([0-9a-f]{64})  ([^\s]+)',line)
            if not m or m[2] in digests:
                raise ValueError('Malformed or duplicated checksum')
            digests[m[2]]=m[1]
        if set(digests)!=REQUIRED-{'SHA256SUMS.txt'}:
            raise ValueError('Incomplete checksum manifest')
        for name,digest in digests.items():
            if hashlib.sha256(z.read(name)).hexdigest()!=digest:
                raise ValueError('Package checksum mismatch: '+name)
        profile=yaml.safe_load(z.read(PROFILE))
        if not isinstance(profile,dict) or profile.get('id')!='G9.9' or profile.get('regression')!={'enabled':True,'path':'tests/'}:
            raise ValueError('Invalid registered G9.9 validation profile')
        targets=profile.get('target_tests')
        if not isinstance(targets,list) or len(targets)<10 or len(targets)!=len(set(targets)):
            raise ValueError('Invalid or insufficient selected validation tests')
        if not {'tests/semantic_audit/test_ae08_benchmark.py','tests/semantic_audit/test_ae08_release.py',
                'tests/semantic_audit/test_ae07_portfolio.py','tests/ae01/test_vertical_slice.py'}.issubset(targets):
            raise ValueError('G9.9 does not select its own source-to-verification tests')
        for path in targets:
            if (not isinstance(path,str) or not path.startswith('tests/') or not path.endswith('.py') or
                    '..' in PurePosixPath(path).parts or '\\' in path):
                raise ValueError('Invalid test target')
            if PREFIX+path not in REQUIRED and (not (repo/path).is_file() or (repo/path).is_symlink()):
                raise ValueError('Missing validation target: '+path)
        for file in FIXTURES:
            if file.endswith('/gold.json'):
                # Labels and exact source hashes are cross-checked by independent evaluator tests.
                import json
                root=PurePosixPath(file).parent
                labels=json.loads(z.read(PREFIX+file))
                files=labels['files']
                actual={p.relative_to(root).as_posix() for p in map(PurePosixPath, FIXTURES)
                        if root in p.parents and p.suffix=='.py'}
                if set(files)!=actual:
                    raise ValueError('Labeled fixture coverage mismatch')
                for relative,digest in files.items():
                    if hashlib.sha256(z.read(PREFIX+str(root/relative))).hexdigest()!=digest:
                        raise ValueError('Fixture label source checksum mismatch')
        return {'profile':'G9.9','files':len(REQUIRED),'selected_tests':len(targets),
                'checksums':'verified','fixture_hashes':'verified','source_branch_only':True}


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--zip',type=Path,required=True)
    p.add_argument('--repository',type=Path,required=True)
    a=p.parse_args(argv)
    try:print(check(a.zip,a.repository));return 0
    except (ValueError,KeyError,OSError,TypeError,zipfile.BadZipFile,UnicodeError) as exc:
        print('AE-08 release error:',exc,file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
