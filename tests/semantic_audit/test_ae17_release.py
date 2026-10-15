"""Release admission negative controls (run by GitHub selected G9.19 profile)."""
import hashlib
import zipfile
from pathlib import Path

import pytest
import importlib.util
CHECKER = Path(__file__).resolve().parents[2] / 'tools/check_ae17_patch.py'
spec = importlib.util.spec_from_file_location('ae17_checker',CHECKER)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
verify, FILES, TOP = checker.verify, checker.FILES, checker.TOP


def make_archive(path,override=None,extra=None):
    override=override or {}
    extra=extra or {}
    data={name:override.get(name,b'x') for name in FILES|TOP-{'SHA256SUMS.txt'}}
    data.update(extra)
    data['SHA256SUMS.txt']=''.join(f'{hashlib.sha256(blob).hexdigest()}  {name}\n' for name,blob in sorted(data.items())).encode()
    with zipfile.ZipFile(path,'w') as archive:
        for name,blob in data.items():archive.writestr(name,blob)
    return path


def test_valid_manifest(tmp_path):
    assert verify(make_archive(tmp_path/'ok.zip'))['status']=='integrity_verified_not_tests_executed'


def test_reject_traversal_dir(tmp_path):
    path=make_archive(tmp_path/'bad.zip')
    with zipfile.ZipFile(path,'a') as archive:archive.writestr('evil/../',b'')
    with pytest.raises(ValueError):verify(path)


def test_reject_extra_member(tmp_path):
    path=make_archive(tmp_path/'bad.zip',extra={'unexpected.py':b'pass'})
    with pytest.raises(ValueError):verify(path)


def test_reject_changed_file(tmp_path):
    path=make_archive(tmp_path/'bad.zip')
    with zipfile.ZipFile(path,'a') as archive:archive.writestr(next(iter(FILES)),b'tampered')
    with pytest.raises(ValueError):verify(path)


def test_reject_missing_member(tmp_path):
    path=tmp_path/'bad.zip'
    with zipfile.ZipFile(path,'w') as archive:archive.writestr('SHA256SUMS.txt',b'')
    with pytest.raises(ValueError):verify(path)
