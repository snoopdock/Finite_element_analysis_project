"""Release negative controls; no claims based on merely existing package files."""
from pathlib import Path
import hashlib
import stat
import zipfile
import pytest
from tools.check_ae10_patch import check,REQUIRED

ROOT=Path(__file__).resolve().parents[2]


def fixture_zip(tmp_path,alter=None):
    files={}
    for name in sorted(REQUIRED-{'SHA256SUMS.txt'}):
        if name.startswith('STAGE1_SECTION_UUIDS/'):
            files[name]=(ROOT/name.removeprefix('STAGE1_SECTION_UUIDS/')).read_bytes()
        else:
            files[name]=b'fixture documentation\n'
    if alter: alter(files)
    files['SHA256SUMS.txt']=''.join(f'{hashlib.sha256(data).hexdigest()}  {name}\n' for name,data in sorted(files.items())).encode()
    out=tmp_path/'release.zip'
    with zipfile.ZipFile(out,'w') as z:
        for name,data in sorted(files.items()):z.writestr(name,data)
    return out


def test_profile_physically_present_and_valid(tmp_path):
    result=check(fixture_zip(tmp_path),ROOT)
    assert result['profile']=='G9.11'
    assert result['test_targets']==11


@pytest.mark.parametrize('missing',[
 'STAGE1_SECTION_UUIDS/validation/profiles/G9.11.yaml',
 'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae10/science.py',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/test_ae10_science.py',
 'STAGE1_SECTION_UUIDS/tests/fixtures/ae10/spec.json'])
def test_missing_members_rejected(tmp_path,missing):
    with pytest.raises(ValueError,match='Missing'):
        check(fixture_zip(tmp_path,lambda d:d.pop(missing)),ROOT)


def test_corrupted_source_rejected(tmp_path):
    p=fixture_zip(tmp_path)
    with zipfile.ZipFile(p) as z:d={name:z.read(name) for name in z.namelist()}
    d['STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae10/science.py']=b'broken'
    with zipfile.ZipFile(p,'w') as z:
        for name,data in d.items():z.writestr(name,data)
    with pytest.raises(ValueError,match='Checksum mismatch'):check(p,ROOT)


@pytest.mark.parametrize('unsafe',['../outside','/etc/passwd','STAGE1_SECTION_UUIDS/__pycache__/x.pyc',
 'STAGE1_SECTION_UUIDS/foo\\bar'])
def test_unsafe_members_rejected(tmp_path,unsafe):
    p=fixture_zip(tmp_path)
    with zipfile.ZipFile(p,'a') as z:z.writestr(unsafe,b'a')
    with pytest.raises(ValueError):check(p,ROOT)


def test_profile_missing_real_test_detected(tmp_path):
    def alter(files):
        k='STAGE1_SECTION_UUIDS/validation/profiles/G9.11.yaml'
        files[k]=files[k].replace(b'tests/semantic_audit/test_ae10_release.py',b'tests/unknown_missing.py')
    with pytest.raises(ValueError,match='Missing declared target'):check(fixture_zip(tmp_path,alter),ROOT)


def test_profile_wrong_identity_detected(tmp_path):
    def alter(files):
        k='STAGE1_SECTION_UUIDS/validation/profiles/G9.11.yaml'
        files[k]=files[k].replace(b'id: G9.11',b'id: G9.12')
    with pytest.raises(ValueError,match='identity'):check(fixture_zip(tmp_path,alter),ROOT)


def test_extra_unhashed_member_detected(tmp_path):
    p=fixture_zip(tmp_path)
    with zipfile.ZipFile(p,'a') as z:z.writestr('extra.txt',b'payload')
    with pytest.raises(ValueError,match='coverage'):check(p,ROOT)


def test_zip_symlink_rejected(tmp_path):
    p=fixture_zip(tmp_path)
    info=zipfile.ZipInfo('STAGE1_SECTION_UUIDS/linked')
    info.create_system=3
    info.external_attr=(stat.S_IFLNK|0o777)<<16
    with zipfile.ZipFile(p,'a') as z:z.writestr(info,'/etc/passwd')
    with pytest.raises(ValueError,match='Symlink'):check(p,ROOT)
