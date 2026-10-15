"""Static-only, read-only AE-17 ZIP admission/membership/checksum check.

Usage: python tools/check_ae17_patch.py PATCH.zip
Does not execute tests or imported patch code.
"""
from __future__ import annotations
import hashlib
import sys
import zipfile
from pathlib import PurePosixPath

ROOT='STAGE1_SECTION_UUIDS/'
FILES={
 ROOT+'audit_engine/semantic_audit/ae17/__init__.py',
 ROOT+'audit_engine/semantic_audit/ae17/investigate.py',
 ROOT+'audit_engine/semantic_audit/ae17/publication.py',
 ROOT+'audit_engine/semantic_audit/ae17/DESIGN_AND_LIMITATIONS.md',
 ROOT+'tools/run_ae17_investigation.py',
 ROOT+'tools/check_ae17_patch.py',
 ROOT+'tests/semantic_audit/test_ae17_investigation.py',
 ROOT+'tests/semantic_audit/test_ae17_release.py',
 ROOT+'validation/profiles/G9.19.yaml',
}
TOP={'README.md','PATCH_MAP.md','VALIDATION_PLAN.md','SHA256SUMS.txt'}


def verify(path):
    with zipfile.ZipFile(path) as archive:
        members=archive.infolist()
        if len(members)>64:raise ValueError('Too many archive members')
        files={};names=set();total=0
        for item in members:
            name=item.filename
            parts=PurePosixPath(name).parts
            if (not name or name.startswith('/') or '\\' in name or ':' in name or
                any(p in ('.','..','') for p in name.split('/')) or
                item.is_dir() or item.filename in names):
                raise ValueError('Unsafe ZIP entry, duplicate name or unexpected directory')
            mode=(item.external_attr >> 16) & 0o170000
            if mode not in (0,0o100000):raise ValueError('Unexpected ZIP member file type')
            if item.file_size>1_500_000:raise ValueError('Oversize ZIP member')
            names.add(name); total+=item.file_size
            if total>4_000_000:raise ValueError('ZIP aggregate budget exceeded')
            files[name]=archive.read(item)
        if names!=FILES|TOP:raise ValueError('Patch ZIP membership differs from declared files')
        manifest=files['SHA256SUMS.txt'].decode('ascii').splitlines()
        seen=set()
        for line in manifest:
            try:digest,name=line.split('  ',1)
            except ValueError as exc:raise ValueError('Malformed checksum row') from exc
            if name in seen or name not in files or name=='SHA256SUMS.txt':
                raise ValueError('Unexpected/duplicate checksum entry')
            if digest != hashlib.sha256(files[name]).hexdigest():
                raise ValueError('Patch checksum mismatch')
            seen.add(name)
        if seen!=names-{'SHA256SUMS.txt'}:raise ValueError('Incomplete patch checksum manifest')
    return {'members':len(names),'checksum_files':len(seen),'status':'integrity_verified_not_tests_executed'}


if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('Usage: check_ae17_patch.py PATCH.zip')
    print(verify(sys.argv[1]))
