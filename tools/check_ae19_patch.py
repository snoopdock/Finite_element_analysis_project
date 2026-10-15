"""Safe source-only AE-19 patch verification, no test execution."""
from __future__ import annotations
import argparse
import hashlib
import re
import stat
import zipfile
from pathlib import Path


def verify(path:Path) -> dict:
    if not path.is_file() or path.stat().st_size>8_000_000:
        raise ValueError('Patch archive absent or oversized')
    with zipfile.ZipFile(path) as z:
        infos=z.infolist()
        if not 18<=len(infos)<=64:raise ValueError('Patch entry count out of bounds')
        names=set();total=0
        for info in infos:
            name=info.filename
            if (name in names or name.startswith('/') or '\\' in name or ':' in name or '\x00' in name or
                any(seg in ('','.','..') for seg in name.split('/')) or
                info.is_dir() or info.flag_bits & 1 or
                stat.S_IFMT((info.external_attr >> 16) & 0xffff) not in (0,stat.S_IFREG)):
                raise ValueError('Unsafe, duplicate or unexpected archive entry')
            names.add(name);total+=info.file_size
            if info.file_size>600_000 or total>4_000_000:raise ValueError('Expanded patch too large')
        required={'README.md','PATCH_MAP.md','VALIDATION_PLAN.md','SHA256SUMS.txt'}
        required|={'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae19/'+name for name in ('__init__.py','evaluate.py','publication.py','DESIGN_AND_LIMITATIONS.md')}
        required|={'STAGE1_SECTION_UUIDS/tests/semantic_audit/'+name for name in ('test_ae19_history.py','test_ae19_release.py')}
        required|={'STAGE1_SECTION_UUIDS/tools/'+name for name in ('run_ae19_history.py','check_ae19_patch.py')}
        required.add('STAGE1_SECTION_UUIDS/validation/profiles/G9.21.yaml')
        base='STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae19_history/'
        required|={base+name for name in ('labels.json','MANIFEST.json')}
        for case in ('H01_g920_initial_failure','H02_g920_corrected_pass'):
            required|={base+'cases/'+case+'/'+f for f in ('step7.txt','step8.txt','step9.txt','step11.txt')}
        if names!=required:raise ValueError('Patch archive exact-member mismatch: missing='+repr(required-names)+' extra='+repr(names-required))
        sums=z.read('SHA256SUMS.txt').decode('ascii').splitlines()
        lines={}
        for line in sums:
            m=re.fullmatch(r'([0-9a-f]{64})  ([^\s]+)',line)
            if not m or m.group(2) in lines:raise ValueError('Invalid or duplicate ZIP checksum')
            lines[m.group(2)]=m.group(1)
        if set(lines)!=names-{'SHA256SUMS.txt'}:raise ValueError('Incomplete checksum inventory')
        for name,digest in lines.items():
            if hashlib.sha256(z.read(name)).hexdigest()!=digest:raise ValueError('ZIP bytes or digest changed')
        return {'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'members':len(infos),
                'expanded_bytes':total,'profile':'G9.21','status':'archive_integrity_only'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('archive',type=Path)
    args=parser.parse_args();print(verify(args.archive))

if __name__=='__main__':main()
