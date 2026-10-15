"""Negative controls for the G9.18 release ZIP checker."""
from __future__ import annotations
import hashlib
import importlib.util
import stat
import zipfile
from pathlib import Path
import pytest

CHECKER=Path(__file__).resolve().parents[2]/'tools/check_ae16_patch.py'


def checker():
    spec=importlib.util.spec_from_file_location('ae16_zip_checker',CHECKER)
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def archive(tmp_path,extra=None,tamper=None,link=False):
    tool=checker()
    contents={name:(b'id: G9.18\ntest_ae16_operations.py\ntest_ae16_release.py\ntest_ae15_flow.py\ntest_ae131_protected_contracts.py\ntest_ae09_investigation.py\nregression:\n'
                    if name==tool.PROFILE else b'controlled') for name in tool.FILES if name!='SHA256SUMS.txt'}
    checks=''.join(hashlib.sha256(b).hexdigest()+'  '+n+'\n' for n,b in sorted(contents.items()))
    contents['SHA256SUMS.txt']=checks.encode('ascii')
    if tamper:contents[tamper]=b'changed after checksum generation'
    file=tmp_path/'patch.zip'
    with zipfile.ZipFile(file,'w',zipfile.ZIP_DEFLATED) as z:
        for n,blob in contents.items():
            if link and n=='README.md':
                info=zipfile.ZipInfo(n);info.external_attr=(stat.S_IFLNK|0o777)<<16
                z.writestr(info,b'/etc/passwd')
            else:z.writestr(n,blob)
        if extra is not None:z.writestr(extra,b'extra')
    return file


def test_accept_exact_controlled_package(tmp_path):checker().validate(archive(tmp_path))


@pytest.mark.parametrize('extra',['../evil','/absolute','STAGE1_SECTION_UUIDS/../escape',
                                   'STAGE1_SECTION_UUIDS/other.py','bad/dir/','x\\escape'])
def test_reject_extra_members_including_directory(tmp_path,extra):
    with pytest.raises(ValueError):checker().validate(archive(tmp_path,extra=extra))


def test_reject_modified_member(tmp_path):
    with pytest.raises(ValueError,match='Checksum'):checker().validate(archive(tmp_path,tamper='README.md'))


def test_reject_symlink_member(tmp_path):
    with pytest.raises(ValueError,match='regular file'):checker().validate(archive(tmp_path,link=True))
