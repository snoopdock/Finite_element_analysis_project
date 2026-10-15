"""GitHub-run static release-checker negative controls."""
import hashlib
import importlib.util
import zipfile
from pathlib import Path

import pytest

CHECKER=Path(__file__).resolve().parents[2]/'tools'/'check_ae18_patch.py'
spec=importlib.util.spec_from_file_location('ae18_checker',CHECKER)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
verify,FILES,TOP=module.verify,module.FILES,module.TOP


def make_archive(path,extra=None):
    blobs={n:b'controlled fixture' for n in (FILES|TOP)-{'SHA256SUMS.txt'}}
    if extra:blobs.update(extra)
    blobs['SHA256SUMS.txt']=''.join(f'{hashlib.sha256(v).hexdigest()}  {k}\n'
                                     for k,v in sorted(blobs.items())).encode()
    with zipfile.ZipFile(path,'w') as bundle:
        for name,blob in sorted(blobs.items()):bundle.writestr(name,blob)
    return path


def test_valid_manifest(tmp_path):
    assert verify(make_archive(tmp_path/'ok.zip'))['status']=='static_integrity_verified_not_tests_executed'


def test_reject_traversal_directory(tmp_path):
    p=make_archive(tmp_path/'bad.zip')
    with zipfile.ZipFile(p,'a') as bundle:bundle.writestr('escape/../',b'')
    with pytest.raises(ValueError):verify(p)


def test_reject_traversal_file(tmp_path):
    p=make_archive(tmp_path/'bad.zip',{'../escape.py':b'pass'})
    with pytest.raises(ValueError):verify(p)


def test_reject_extra_member(tmp_path):
    with pytest.raises(ValueError):verify(make_archive(tmp_path/'bad.zip',{'unlisted.txt':b'bad'}))


def test_reject_missing_member(tmp_path):
    p=tmp_path/'bad.zip'
    with zipfile.ZipFile(p,'w') as bundle:bundle.writestr('SHA256SUMS.txt',b'')
    with pytest.raises(ValueError):verify(p)


def test_reject_duplicate_member(tmp_path):
    p=make_archive(tmp_path/'bad.zip')
    with zipfile.ZipFile(p,'a') as bundle:bundle.writestr(next(iter(FILES)),b'changed')
    with pytest.raises(ValueError):verify(p)
