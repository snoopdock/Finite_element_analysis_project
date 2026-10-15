"""Strict G9.18 release ZIP membership/path/type/size/digest admission."""
from __future__ import annotations

import hashlib
import stat
import sys
import zipfile
from pathlib import Path

ROOT='STAGE1_SECTION_UUIDS/'
PROFILE=ROOT+'validation/profiles/G9.18.yaml'
FILES=frozenset({
    ROOT+'audit_engine/semantic_audit/ae16/__init__.py',
    ROOT+'audit_engine/semantic_audit/ae16/operations.py',
    ROOT+'audit_engine/semantic_audit/ae16/publication.py',
    ROOT+'audit_engine/semantic_audit/ae16/DESIGN_AND_LIMITATIONS.md',
    ROOT+'tools/run_ae16_operations.py',
    ROOT+'tools/check_ae16_patch.py',
    ROOT+'tests/semantic_audit/test_ae16_operations.py',
    ROOT+'tests/semantic_audit/test_ae16_release.py',
    PROFILE,
    'README.md','PATCH_MAP.md','VALIDATION_PLAN.md','SHA256SUMS.txt',
})


def validate(path:Path)->None:
    with zipfile.ZipFile(path) as z:
        infos=z.infolist()
        if len(infos)!=len(FILES):raise ValueError('Release ZIP member count differs')
        names=set();size=0
        for info in infos:
            n=info.filename
            if (n in names or info.is_dir() or n.endswith('/') or n.startswith('/') or
                '\\' in n or ':' in n or any(x in ('','.','..') for x in n.split('/'))):
                raise ValueError(f'Unsafe or duplicate release member: {n}')
            mode=stat.S_IFMT(info.external_attr>>16)
            if mode not in (0,stat.S_IFREG):raise ValueError(f'Not a regular file: {n}')
            if (info.file_size>5_000_000 or info.compress_size==0 and info.file_size or
                info.file_size>500*max(1,info.compress_size)):
                raise ValueError(f'Excessive compressed member: {n}')
            size+=info.file_size
            if size>12_000_000:raise ValueError('Excessive uncompressed release size')
            names.add(n)
        if names!=FILES:raise ValueError(f'Membership differs: missing={FILES-names}, extra={names-FILES}')
        hashes={}
        for line in z.read('SHA256SUMS.txt').decode('ascii').splitlines():
            digest,sep,name=line.partition('  ')
            if (not sep or len(digest)!=64 or any(ch not in '0123456789abcdef' for ch in digest) or
                name=='SHA256SUMS.txt' or name not in names or name in hashes):
                raise ValueError('Malformed release checksum manifest')
            hashes[name]=digest
        if set(hashes)!=names-{'SHA256SUMS.txt'}:raise ValueError('Incomplete release checksum manifest')
        for n,digest in hashes.items():
            if hashlib.sha256(z.read(n)).hexdigest()!=digest:raise ValueError(f'Checksum mismatch: {n}')
        profile=z.read(PROFILE).decode('utf-8')
        if not all(token in profile for token in ('id: G9.18','test_ae16_operations.py',
                   'test_ae16_release.py','test_ae15_flow.py','test_ae131_protected_contracts.py',
                   'test_ae09_investigation.py','regression:')):
            raise ValueError('G9.18 validation scope or profile is missing')


if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('Usage: python tools/check_ae16_patch.py ARCHIVE.zip')
    validate(Path(sys.argv[1]));print('G9.18 release ZIP integrity and exact membership validated')
