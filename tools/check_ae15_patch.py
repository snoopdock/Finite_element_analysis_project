"""G9.17 strict release ZIP member, path, file type and checksum validator."""
from __future__ import annotations
import hashlib
import stat
import sys
import zipfile
from pathlib import Path

ROOT='STAGE1_SECTION_UUIDS/'
PROFILE=ROOT+'validation/profiles/G9.17.yaml'
FILES=frozenset({
    ROOT+'audit_engine/semantic_audit/ae15/__init__.py',
    ROOT+'audit_engine/semantic_audit/ae15/flow.py',
    ROOT+'audit_engine/semantic_audit/ae15/publication.py',
    ROOT+'audit_engine/semantic_audit/ae15/DESIGN_AND_LIMITATIONS.md',
    ROOT+'tools/run_ae15_flow.py',
    ROOT+'tools/check_ae15_patch.py',
    ROOT+'tests/semantic_audit/test_ae15_flow.py',
    ROOT+'tests/semantic_audit/test_ae15_release.py',
    PROFILE,'README.md','PATCH_MAP.md','LOCAL_VALIDATION_RESULTS.md','SHA256SUMS.txt',
    'VALIDATION_LOGS/selected.log','VALIDATION_LOGS/fresh_install_selected.log',
    'VALIDATION_LOGS/full_regression.log','VALIDATION_LOGS/full_regression.exit',
})


def validate(path:Path)->None:
    with zipfile.ZipFile(path) as z:
        infos=z.infolist()
        if len(infos)!=len(FILES):raise ValueError('Member count differs')
        seen=set();total=0
        for entry in infos:
            n=entry.filename
            if (n in seen or entry.is_dir() or n.endswith('/') or n.startswith('/') or '\\' in n or
                ':' in n or any(x in ('','.','..') for x in n.split('/'))):
                raise ValueError(f'Unsafe or repeated ZIP entry: {n}')
            seen.add(n)
            mode=stat.S_IFMT(entry.external_attr>>16)
            if mode not in (0,stat.S_IFREG):raise ValueError(f'Nonregular ZIP entry: {n}')
            if (entry.file_size>8_000_000 or (entry.compress_size==0 and entry.file_size>0) or
                entry.file_size>500*max(1,entry.compress_size)):
                raise ValueError(f'Excessive ZIP member: {n}')
            total+=entry.file_size
            if total>16_000_000:raise ValueError('Excessive total decompression size')
        if seen!=FILES:raise ValueError(f'Unexpected archive membership: missing {FILES-seen}, extra {seen-FILES}')
        hashes={}
        for line in z.read('SHA256SUMS.txt').decode('ascii').splitlines():
            digest,sep,n=line.partition('  ')
            if not sep or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest) or n in hashes or n not in seen or n=='SHA256SUMS.txt':
                raise ValueError('Malformed checksum manifest')
            hashes[n]=digest
        if set(hashes)!=seen-{'SHA256SUMS.txt'}:raise ValueError('Incomplete checksum manifest')
        for n,digest in hashes.items():
            if hashlib.sha256(z.read(n)).hexdigest()!=digest:
                raise ValueError(f'Checksum mismatch: {n}')
        profile=z.read(PROFILE).decode('utf8')
        required=('id: G9.17','test_ae15_flow.py','test_ae15_release.py','test_ae14_lexical_semantics.py',
                  'test_ae131_protected_contracts.py','regression:')
        if not all(s in profile for s in required):raise ValueError('Missing required validation scope')

if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('python tools/check_ae15_patch.py FILE.zip')
    validate(Path(sys.argv[1]));print('G9.17 ZIP exact-membership and SHA-256 validation passed')
