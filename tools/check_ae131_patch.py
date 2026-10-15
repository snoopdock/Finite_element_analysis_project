"""G9.15 release checker: validate all ZIP members before installation.

Usage: python tools/check_ae131_patch.py AE-13_1_...zip
Checks byte hashes and exact file membership; does not execute archive code.
"""
from __future__ import annotations
import hashlib
import os
import stat
import sys
import zipfile
from pathlib import PurePosixPath,Path

PROFILE='STAGE1_SECTION_UUIDS/validation/profiles/G9.15.yaml'
FILES={
'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/findings/factory.py',
'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/high_assurance/execution.py',
'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/verification/integrity.py',
'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/verification/models.py',
'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/verification/service.py',
'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/rules/evaluator.py',
'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/rules/execution.py',
'STAGE1_SECTION_UUIDS/tests/semantic_audit/test_ae131_protected_contracts.py',
'STAGE1_SECTION_UUIDS/tests/semantic_audit/test_ae131_release.py',
' STAGE1_SECTION_UUIDS/validation/profiles/G9.15.yaml'.strip(),
'STAGE1_SECTION_UUIDS/tools/check_ae131_patch.py',
'README.md','PATCH_MAP.md','LOCAL_VALIDATION_RESULTS.md','SHA256SUMS.txt',
'VALIDATION_LOGS/selected.log','VALIDATION_LOGS/full_regression.log',
'VALIDATION_LOGS/full_regression.exit','VALIDATION_LOGS/fresh_install_selected.log',
'VALIDATION_LOGS/policy_audit_isolated.log','VALIDATION_LOGS/solver_patch_isolated.log','VALIDATION_LOGS/solver_baseline_isolated.log',
}

def validate(path:Path):
    with zipfile.ZipFile(path) as z:
        infos=z.infolist()
        if len(infos)!=len(FILES) or len(infos)>100:
            raise ValueError('Incorrect ZIP member count')
        found=set();total=0
        for info in infos:
            n=info.filename
            q=PurePosixPath(n)
            if (n in found or n.startswith('/') or '\\' in n or ':' in n or
                any(t in ('','.','..') for t in n.split('/')) or str(q)!=n or n.endswith('/')):
                raise ValueError(f'Unsafe or repeated member: {n!r}')
            found.add(n)
            mode=info.external_attr>>16
            if stat.S_IFMT(mode) not in (0,stat.S_IFREG):
                raise ValueError('Nonregular ZIP member')
            if (info.file_size>8_000_000 or info.compress_size==0 and info.file_size>0 or
                info.file_size>max(1,info.compress_size)*500):
                raise ValueError('Oversized or extreme compression member')
            total+=info.file_size
            if total>14_000_000:
                raise ValueError('Too much uncompressed data')
        if found!=FILES:raise ValueError(f'Membership mismatch: missing={sorted(FILES-found)}, extra={sorted(found-FILES)}')
        lines=z.read('SHA256SUMS.txt').decode('ascii').splitlines()
        checked=set()
        for line in lines:
            digest, sep, name=line.partition('  ')
            if not sep or len(digest)!=64 or name in checked or name not in found or name=='SHA256SUMS.txt':
                raise ValueError('Malformed checksum manifest')
            if hashlib.sha256(z.read(name)).hexdigest()!=digest:
                raise ValueError('ZIP member digest mismatch: '+name)
            checked.add(name)
        if checked!=found-{'SHA256SUMS.txt'}:
            raise ValueError('Missing checksum coverage')
        profile=z.read(PROFILE).decode()
        if 'id: G9.15' not in profile or 'test_ae131_protected_contracts.py' not in profile or 'regression:' not in profile:
            raise ValueError('Wrong validation profile')
    return True

if __name__=='__main__':
    if len(sys.argv)!=2:
        raise SystemExit('Usage: check_ae131_patch.py RELEASE.zip')
    validate(Path(sys.argv[1]))
    print('G9.15 patch validated: safe members, complete SHA256 and profile')
