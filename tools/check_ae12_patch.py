"""AE-12 release gate: validate *archive bytes* and the registered G9.13 profile."""
from __future__ import annotations

import hashlib
import io
from pathlib import Path, PurePosixPath
import stat
import sys
import zipfile

import yaml

PREFIX='STAGE1_SECTION_UUIDS/'
REQUIRED={
    'README.md', 'PATCH_MAP.md','LOCAL_VALIDATION_RESULTS.md','SHA256SUMS.txt',
    PREFIX+'audit_engine/semantic_audit/ae12/__init__.py',
    PREFIX+'audit_engine/semantic_audit/ae12/__main__.py',
    PREFIX+'audit_engine/semantic_audit/ae12/analyze.py',
    PREFIX+'audit_engine/semantic_audit/ae12/publication.py',
    PREFIX+'audit_engine/semantic_audit/ae12/METHOD_AND_LIMITATIONS.md',
    PREFIX+'audit_engine/semantic_audit/ae12/CODE_AUDIT_ROADMAP.md',
    PREFIX+'tests/semantic_audit/test_ae12_code_failures.py',
    PREFIX+'tests/semantic_audit/test_ae12_release.py',
    PREFIX+'tests/fixtures/ae12/risk_patterns.py',
    PREFIX+'tests/fixtures/ae12/expected.json',
    PREFIX+'tests/fixtures/ae12/policy.json',
    PREFIX+'tools/check_ae12_patch.py',
    PREFIX+'validation/profiles/G9.13.yaml',
}


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_bytes(raw:bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        entries=[info for info in z.infolist() if not info.is_dir()]
        names=[info.filename for info in entries]
        if len(names)!=len(set(names)):
            raise ValueError('Duplicate ZIP names')
        if not REQUIRED.issubset(set(names)):
            raise ValueError('Missing required profile, source, test or release file: '+str(sorted(REQUIRED-set(names))))
        for entry in entries:
            name=entry.filename
            parts=PurePosixPath(name).parts
            if ('\\' in name or not parts or name.startswith('/') or
                any(part in ('.','..','') for part in parts) or
                (name not in ('README.md','PATCH_MAP.md','LOCAL_VALIDATION_RESULTS.md','SHA256SUMS.txt')
                 and not name.startswith(PREFIX) and not name.startswith('VALIDATION_LOGS/')) or
                any(part in ('__pycache__','.pytest_cache') for part in parts) or
                name.endswith(('.pyc','.pyo'))):
                raise ValueError('Unsafe ZIP member: '+name)
            mode=(entry.external_attr>>16)
            if stat.S_ISLNK(mode):
                raise ValueError('Symlink in release archive: '+name)
            if entry.file_size>5_000_000:
                raise ValueError('Unexpected oversized release member')
        checksum_lines=z.read('SHA256SUMS.txt').decode('utf-8').splitlines()
        sums={}
        for line in checksum_lines:
            if len(line)<67 or line[64:66]!='  ' or line[:64].lower()!=line[:64]:
                raise ValueError('Malformed checksum manifest')
            name=line[66:]
            if name in sums:
                raise ValueError('Duplicate checksum entry')
            sums[name]=line[:64]
        actual=set(names)-{'SHA256SUMS.txt'}
        if set(sums)!=actual:
            raise ValueError('Checksum manifest does not match ZIP membership')
        if any(_digest(z.read(name))!=digest for name,digest in sums.items()):
            raise ValueError('Checksum mismatch')
        profile=yaml.safe_load(z.read(PREFIX+'validation/profiles/G9.13.yaml'))
        if profile.get('id')!='G9.13' or not isinstance(profile.get('target_tests'),list):
            raise ValueError('Invalid manual profile')
        targets=profile['target_tests']
        if not targets or len(set(targets))!=len(targets):
            raise ValueError('Missing or repeated test targets')
        for test in targets:
            if not isinstance(test,str) or not test.startswith('tests/') or not test.endswith('.py'):
                raise ValueError('Invalid test selector: '+str(test))
            # Existing repo tests are not duplicated in the ZIP. New AE-12 tests must be.
            if 'ae12' in test and PREFIX+test not in names:
                raise ValueError('G9.13 references missing packaged test: '+test)
            if not (Path(__file__).resolve().parents[1]/test).is_file():
                raise ValueError('G9.13 references nonexistent repository test: '+test)
        if profile.get('regression')!={'enabled':True,'path':'tests/'}:
            raise ValueError('Invalid regression coverage selection')
        return {'valid':True,'members':len(names),'profile':'G9.13','test_targets':len(targets)}


def main(argv=None):
    argv=list(argv if argv is not None else sys.argv[1:])
    if len(argv)!=1:
        print('Usage: python tools/check_ae12_patch.py patch.zip',file=sys.stderr)
        return 2
    try:
        print(validate_bytes(Path(argv[0]).read_bytes()))
    except (OSError,ValueError,KeyError,zipfile.BadZipFile,yaml.YAMLError) as exc:
        print('AE-12 patch rejected: '+str(exc),file=sys.stderr)
        return 1
    return 0

if __name__=='__main__':
    raise SystemExit(main())
