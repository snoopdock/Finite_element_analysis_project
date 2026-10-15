"""AE-13 D1-D3 release validator: verify the actual ZIP and manual profile.

Unlike prior patch checker, validates *every ZIP entry*, including directories.
It does not extract user-controlled archives. Test paths are checked against
an explicitly supplied checkout (or repository containing this checker).
"""
from __future__ import annotations
import hashlib
import io
from pathlib import Path, PurePosixPath
import stat
import sys
import zipfile
import yaml

PREFIX='STAGE1_SECTION_UUIDS/'
BASE_FILES=('README.md','PATCH_MAP.md','LOCAL_VALIDATION_RESULTS.md','SHA256SUMS.txt')
CODE=[
'audit_engine/semantic_audit/ae13/__init__.py',
'audit_engine/semantic_audit/ae13/__main__.py',
'audit_engine/semantic_audit/ae13/identity.py',
'audit_engine/semantic_audit/ae13/admission.py',
'audit_engine/semantic_audit/ae13/legacy.py',
'audit_engine/semantic_audit/ae13/bindings.py',
'audit_engine/semantic_audit/ae13/benchmark.py',
'audit_engine/semantic_audit/ae13/DESIGN_AND_LIMITATIONS.md',
'tests/semantic_audit/test_ae13_legacy_adapter.py',
'tests/semantic_audit/test_ae13_many_to_many.py',
'tests/semantic_audit/test_ae13_benchmarks.py',
'tests/semantic_audit/test_ae13_release.py',
'tools/check_ae13_patch.py',
'validation/profiles/G9.14.yaml']
REQUIRED=set(BASE_FILES)|{PREFIX+item for item in CODE}
MAX_FILES=90
MAX_TOTAL_UNCOMPRESSED=15_000_000
MAX_MEMBER=4_000_000


def validate_bytes(data:bytes,*,repo_root:Path) -> dict:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        files=z.infolist()
        if len(files)>MAX_FILES or len(files)<len(REQUIRED):
            raise ValueError('Unexpected archive member count')
        paths=[]
        total=0
        for entry in files:
            path=entry.filename
            if entry.is_dir():
                raise ValueError('Directory entries are not permitted in this release archive')
            pp=PurePosixPath(path)
            parts=path.split('/')
            if (path.startswith('/') or '\\' in path or not parts or any(p in ('','.','..') for p in parts)
                or pp.as_posix()!=path or '\x00' in path
                or not (path in BASE_FILES or path.startswith(PREFIX) or path.startswith('VALIDATION_LOGS/'))
                or any(seg in ('__pycache__','.pytest_cache') for seg in parts)
                or path.endswith(('.pyc','.pyo'))):
                raise ValueError('Unsafe archive member: '+path)
            unix_mode=entry.external_attr>>16
            if stat.S_IFMT(unix_mode) not in (0,stat.S_IFREG):
                raise ValueError('Archive contains nonregular member')
            if entry.file_size>MAX_MEMBER:
                raise ValueError('Oversize member')
            if entry.file_size and entry.compress_size and entry.file_size>2000*entry.compress_size:
                raise ValueError('Unsafe compression ratio')
            total+=entry.file_size
            paths.append(path)
        if total>MAX_TOTAL_UNCOMPRESSED or len(paths)!=len(set(paths)):
            raise ValueError('Archive total bytes or duplicate paths invalid')
        missing=REQUIRED-set(paths)
        if missing:
            raise ValueError('Missing required patch members: '+str(sorted(missing)))
        if not all(p in REQUIRED or p.startswith('VALIDATION_LOGS/') for p in paths):
            raise ValueError('Unexpected archive member')
        checksum_lines=z.read('SHA256SUMS.txt').decode('utf-8').splitlines()
        sums={}
        for line in checksum_lines:
            if len(line)<67 or line[64:66]!='  ' or not all(c in '0123456789abcdef' for c in line[:64]):
                raise ValueError('Invalid manifest line')
            name=line[66:]
            if name in sums:
                raise ValueError('Duplicate checksum entry')
            sums[name]=line[:64]
        if set(sums)!=set(paths)-{'SHA256SUMS.txt'}:
            raise ValueError('Manifest membership mismatch')
        if any(hashlib.sha256(z.read(name)).hexdigest()!=digest for name,digest in sums.items()):
            raise ValueError('Checksum mismatch')
        profile=yaml.safe_load(z.read(PREFIX+'validation/profiles/G9.14.yaml'))
        if not isinstance(profile,dict) or profile.get('id')!='G9.14':
            raise ValueError('Wrong registered validation profile')
        targets=profile.get('target_tests')
        if not isinstance(targets,list) or not targets or len(set(targets))!=len(targets):
            raise ValueError('Missing/duplicate profile tests')
        if profile.get('regression')!={'enabled':True,'path':'tests/'}:
            raise ValueError('Profile regression must cover tests/')
        for t in targets:
            if not isinstance(t,str) or not t.startswith('tests/') or not t.endswith('.py') or any(part in ('.','..','') for part in t.split('/')):
                raise ValueError('Unsafe test target')
            if not (repo_root/t).is_file():
                raise ValueError('Missing test target in checkout: '+t)
            if 'ae13' in t and PREFIX+t not in paths:
                raise ValueError('New AE-13 target omitted from ZIP')
        return {'verified':True,'profile':'G9.14','members':len(paths),'selected_test_files':len(targets)}


def main(argv=None):
    from argparse import ArgumentParser
    p=ArgumentParser();p.add_argument('zip');p.add_argument('--repo-root',type=Path,default=Path(__file__).resolve().parents[1])
    args=p.parse_args(argv)
    try:print(validate_bytes(Path(args.zip).read_bytes(),repo_root=args.repo_root))
    except (OSError,ValueError,TypeError,zipfile.BadZipFile,yaml.YAMLError) as e:
        print('AE13 release invalid: '+str(e),file=sys.stderr)
        return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
