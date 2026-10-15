"""AE-11 release gate over physical ZIP bytes, not working-tree promises."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

import yaml

PROFILE = 'STAGE1_SECTION_UUIDS/validation/profiles/G9.12.yaml'
FILES = {
 'README.md','PATCH_MAP.md','LOCAL_VALIDATION_RESULTS.md','SHA256SUMS.txt',PROFILE,
 'STAGE1_SECTION_UUIDS/tools/check_ae11_patch.py',
 *('STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae11/'+name for name in
   ('__init__.py','__main__.py','numerics.py','publication.py','METHOD_AND_LIMITATIONS.md')),
 *('STAGE1_SECTION_UUIDS/tests/semantic_audit/'+name for name in
   ('test_ae11_fem.py','test_ae11_release.py')),
 *('STAGE1_SECTION_UUIDS/tests/fixtures/ae11/'+name for name in ('spec.json','bar_problem.json')),
}

def check(archive:Path|str, repository_root:Path|str|None=None)->dict:
    root=Path(repository_root) if repository_root else None
    with zipfile.ZipFile(archive) as z:
        members={}
        for info in z.infolist():
            name=info.filename
            if info.is_dir():continue
            parts=PurePosixPath(name).parts
            if (name.startswith('/') or '\\' in name or '\x00' in name or
                not parts or any(p in ('','..','.') for p in name.split('/')) or
                ':' in parts[0] or any(p=='__pycache__' for p in parts) or
                name.endswith(('.pyc','.pyo'))):
                raise ValueError('Unsafe ZIP member: '+name)
            if stat.S_IFMT(info.external_attr>>16)==stat.S_IFLNK:
                raise ValueError('Symlink member prohibited')
            if info.file_size > 2_000_000 or name in members:
                raise ValueError('Oversized or duplicated file')
            members[name]=z.read(name)
    if not FILES.issubset(members):
        raise ValueError('Missing AE-11 files: '+repr(sorted(FILES-set(members))))
    manifest=members['SHA256SUMS.txt'].decode('utf-8').splitlines()
    digests={}
    for line in manifest:
        match=re.fullmatch(r'([0-9a-f]{64})  (.+)',line)
        if not match or match[2] in digests:
            raise ValueError('Invalid or duplicated SHA256SUMS entry')
        digests[match[2]]=match[1]
    if set(digests)!=set(members)-{'SHA256SUMS.txt'}:
        raise ValueError('Incomplete release checksum coverage')
    for name,digest in digests.items():
        if hashlib.sha256(members[name]).hexdigest()!=digest:
            raise ValueError('Modified ZIP member: '+name)
    profile=yaml.safe_load(members[PROFILE])
    if not isinstance(profile,dict) or profile.get('id')!='G9.12' or profile.get('regression')!={'enabled':True,'path':'tests/'}:
        raise ValueError('Missing G9.12 validation contract')
    tests=profile.get('target_tests')
    if not isinstance(tests,list) or not tests or len(set(tests))!=len(tests):
        raise ValueError('Invalid target selection')
    if 'tests/semantic_audit/test_ae11_fem.py' not in tests or 'tests/semantic_audit/test_ae11_release.py' not in tests:
        raise ValueError('AE-11 targets not selected')
    for test in tests:
        if not isinstance(test,str) or not test.startswith('tests/') or '..' in PurePosixPath(test).parts:
            raise ValueError('Unsafe test path')
        member='STAGE1_SECTION_UUIDS/'+test
        if member not in members and (root is None or not (root/test).is_file()):
            raise ValueError('Missing profile target: '+test)
    base='STAGE1_SECTION_UUIDS/tests/fixtures/ae11/'
    spec=json.loads(members[base+'spec.json'])
    artifact=spec['artifact']
    if artifact['path']!='bar_problem.json' or hashlib.sha256(members[base+'bar_problem.json']).hexdigest()!=artifact['sha256']:
        raise ValueError('FEM gold-fixture integrity failed')
    return {'profile':'G9.12','members':len(members),'test_targets':len(tests)}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('archive');p.add_argument('--repository-root')
    a=p.parse_args()
    print(json.dumps(check(a.archive,a.repository_root),sort_keys=True))
