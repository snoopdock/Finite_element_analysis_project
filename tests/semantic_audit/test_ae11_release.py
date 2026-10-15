"""Negative ZIP-level release tests guard against repeating missing-profile failures."""
import hashlib
import io
from pathlib import Path
import zipfile

import pytest

from tools.check_ae11_patch import check

@pytest.fixture
def archive(tmp_path):
    """A complete synthetic package from *installed* files, no skipped CI tests."""
    from tools.check_ae11_patch import FILES
    root=Path(__file__).resolve().parents[2]
    members={}
    for path in sorted(FILES-{'SHA256SUMS.txt'}):
        if path.startswith('STAGE1_SECTION_UUIDS/'):
            member=root/path.removeprefix('STAGE1_SECTION_UUIDS/')
            members[path]=member.read_bytes()
        else:
            members[path]=(path+'\n').encode()
    members['SHA256SUMS.txt']=''.join(
        hashlib.sha256(data).hexdigest()+'  '+name+'\n'
        for name,data in sorted(members.items())).encode()
    dest=tmp_path/'synthetic_package.zip'
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in members.items():z.writestr(name,data)
    return dest

def rewritemember(input_zip,output,modify):
    with zipfile.ZipFile(input_zip) as z,zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as dst:
        for member in z.infolist():
            if member.is_dir():continue
            new=modify(member.filename,z.read(member.filename))
            if new is not None:
                dst.writestr(member.filename,new)

def test_release_gate_real_archive(archive):
    result=check(archive,Path(__file__).resolve().parents[2])
    assert result['profile']=='G9.12'
    assert result['test_targets']>=6

@pytest.mark.parametrize('target',[
 'STAGE1_SECTION_UUIDS/validation/profiles/G9.12.yaml',
 'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae11/numerics.py',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/test_ae11_fem.py',
])
def test_missing_mandatory_file_is_rejected(tmp_path,archive,target):
    candidate=tmp_path/'candidate.zip'
    rewritemember(archive,candidate,lambda n,b:None if n==target else b)
    with pytest.raises(ValueError):check(candidate,Path(__file__).resolve().parents[2])

def test_corrupted_checksum_rejected(tmp_path,archive):
    candidate=tmp_path/'bad.zip'
    rewritemember(archive,candidate,lambda n,b:b+b'changed' if n.endswith('/numerics.py') else b)
    with pytest.raises(ValueError,match='Modified'):
        check(candidate,Path(__file__).resolve().parents[2])

def test_path_traversal_member_rejected(tmp_path,archive):
    candidate=tmp_path/'bad.zip'
    with zipfile.ZipFile(archive) as z,zipfile.ZipFile(candidate,'w') as dst:
        for n in z.namelist():dst.writestr(n,z.read(n))
        dst.writestr('../escape.py','x')
    with pytest.raises(ValueError,match='Unsafe'):
        check(candidate,Path(__file__).resolve().parents[2])

def test_invalid_profile_test_path_rejected(tmp_path,archive):
    import yaml
    candidate=tmp_path/'bad.zip'
    prof='STAGE1_SECTION_UUIDS/validation/profiles/G9.12.yaml'
    def modify(n,b):
        if n==prof:
            cfg=yaml.safe_load(b);cfg['target_tests'].append('tests/missing_AE_11_file.py')
            return yaml.safe_dump(cfg).encode()
        return b
    rewritemember(archive,candidate,modify)
    with pytest.raises(ValueError):check(candidate,Path(__file__).resolve().parents[2])
