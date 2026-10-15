"""Static integrity verifier for the G9.22 distribution ZIP. NO pytest execution."""
from __future__ import annotations
import hashlib
import pathlib
import stat
import sys
import zipfile

MANDATORY={
 'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae20/__init__.py',
 'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae20/evaluate.py',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/test_ae20_historical_oracles.py',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/test_ae20_behavioral_oracles.py',
 'STAGE1_SECTION_UUIDS/validation/profiles/G9.22.yaml',
}
MAX_MEMBERS=64
MAX_MEMBER=500_000
MAX_TOTAL=2_000_000


def verify(path):
    with zipfile.ZipFile(path) as archive:
        infos=archive.infolist()
        if not infos or len(infos)>MAX_MEMBERS:
            raise ValueError('Invalid archive size')
        actual=set();sizes=0
        for item in infos:
            name=item.filename
            if name in actual or name.startswith('/') or '\\' in name or '\x00' in name or ':' in name:
                raise ValueError('Duplicate or unsafe ZIP member')
            parts=name.rstrip('/').split('/')
            if any(p in ('','.','..') for p in parts):
                raise ValueError('ZIP traversal or invalid member')
            kind=(item.external_attr >>16) & 0o170000
            if item.is_dir() or kind not in (0,stat.S_IFREG):
                raise ValueError('Unsupported ZIP member type')
            if item.file_size > MAX_MEMBER:
                raise ValueError('Oversized ZIP member')
            sizes+=item.file_size
            if sizes>MAX_TOTAL:raise ValueError('Unbounded archive expansion')
            actual.add(name)
        if 'SHA256SUMS.txt' not in actual or not MANDATORY.issubset(actual):
            raise ValueError('Missing required release files')
        entries={}
        for line in archive.read('SHA256SUMS.txt').decode('ascii').splitlines():
            digest,rel=line.split('  ',1)
            if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest) or rel in entries:
                raise ValueError('Malformed checksum manifest')
            entries[rel]=digest
        if set(entries)!=actual-{'SHA256SUMS.txt'}:
            raise ValueError('Unexpected or missing checksum-manifest members')
        for name,digest in entries.items():
            if hashlib.sha256(archive.read(name)).hexdigest()!=digest:
                raise ValueError('ZIP member integrity check failed: '+name)
        return {'members':len(actual),'total_uncompressed_bytes':sizes,
                'archive_sha256':hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()}

if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('Usage: check_ae20_patch.py RELEASE.zip')
    print(verify(sys.argv[1]))
