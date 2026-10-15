"""Release-gate negative tests use constructed ZIPs, also runnable on GitHub."""
import copy
import hashlib
import io
from pathlib import Path
import zipfile

import pytest

from tools.check_ae12_patch import PREFIX,REQUIRED,validate_bytes

ROOT=Path(__file__).resolve().parents[2]


def _archive(modify=None):
    payload={}
    for name in REQUIRED-{'SHA256SUMS.txt'}:
        if name.startswith(PREFIX):
            payload[name]=(ROOT/name[len(PREFIX):]).read_bytes()
        else:
            payload[name]=b'AE-12 packaging test document\n'
    if modify is not None:
        modify(payload)
    checks=''.join(hashlib.sha256(payload[n]).hexdigest()+'  '+n+'\n' for n in sorted(payload))
    payload['SHA256SUMS.txt']=checks.encode()
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name in sorted(payload):z.writestr(name,payload[name])
    return out.getvalue()


def test_constructed_package_with_real_files_is_accepted():
    assert validate_bytes(_archive())['profile']=='G9.13'


@pytest.mark.parametrize('name',[
    PREFIX+'validation/profiles/G9.13.yaml',
    PREFIX+'audit_engine/semantic_audit/ae12/analyze.py',
    PREFIX+'tests/semantic_audit/test_ae12_code_failures.py',
    'README.md',
])
def test_required_missing_rejected(name):
    def drop(files):files.pop(name)
    with pytest.raises(ValueError):validate_bytes(_archive(drop))


def test_hash_tampering_rejected():
    raw=_archive()
    with zipfile.ZipFile(io.BytesIO(raw)) as inp:
        files={n:inp.read(n) for n in inp.namelist()}
    files[PREFIX+'audit_engine/semantic_audit/ae12/analyze.py']+=b'# altered'
    target=io.BytesIO()
    with zipfile.ZipFile(target,'w') as z:
        for name,data in files.items():z.writestr(name,data)
    with pytest.raises(ValueError,match='Checksum mismatch'):validate_bytes(target.getvalue())


@pytest.mark.parametrize('unsafe',[
    '../forbidden.txt',
    PREFIX+'audit_engine/__pycache__/evil.pyc',
    'MAIN_BRANCH/.github/workflows/alter.yml',
])
def test_unsafe_or_unapproved_member_rejected(unsafe):
    with pytest.raises(ValueError):validate_bytes(_archive(lambda f:f.update({unsafe:b'wrong'})))


def test_profile_test_path_forgery_rejected():
    name=PREFIX+'validation/profiles/G9.13.yaml'
    def change(files):files[name]=files[name].replace(b'test_ae12_code_failures.py',b'not_present_ae12.py')
    with pytest.raises(ValueError,match='missing packaged test'):validate_bytes(_archive(change))


def test_bad_regression_selector_rejected():
    name=PREFIX+'validation/profiles/G9.13.yaml'
    def change(files):files[name]=files[name].replace(b'path: tests/',b'path: fake-tests/')
    with pytest.raises(ValueError,match='regression'):validate_bytes(_archive(change))


def test_duplicate_zip_path_rejected():
    raw=_archive()
    out=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as inp,zipfile.ZipFile(out,'w') as z:
        for n in inp.namelist():z.writestr(n,inp.read(n))
        z.writestr('README.md',b'bad')
    with pytest.raises(ValueError,match='Duplicate'):validate_bytes(out.getvalue())


def test_existing_profile_target_missing_rejected():
    name=PREFIX+'validation/profiles/G9.13.yaml'
    def change(files):files[name]=files[name].replace(b'test_ae09_investigation.py',b'test_ae09_missing.py')
    with pytest.raises(ValueError, match='nonexistent repository test'):validate_bytes(_archive(change))
