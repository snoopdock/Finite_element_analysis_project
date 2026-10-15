"""Adversarial release validation; physical G9.10 profile must always ship."""
import hashlib
import io
from pathlib import Path
import zipfile
import pytest
from tools.check_ae09_patch import check

ROOT=Path(__file__).resolve().parents[2]
SOURCE={
 'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae09/__init__.py',
 'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae09/__main__.py',
 'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae09/investigate.py',
 'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae09/publication.py',
 'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae09/METHOD_AND_LIMITATIONS.md',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/test_ae09_investigation.py',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/test_ae09_release.py',
 'STAGE1_SECTION_UUIDS/tools/check_ae09_patch.py',
 'STAGE1_SECTION_UUIDS/validation/profiles/G9.10.yaml',
}

def local_zip(tmp_path,alter=None):
    from tools.check_ae09_patch import REQUIRED
    p=tmp_path/'sample.zip'
    content={}
    for name in sorted(REQUIRED-{'SHA256SUMS.txt'}):
        if name.startswith('STAGE1_SECTION_UUIDS/'):
            content[name]=(ROOT/name.removeprefix('STAGE1_SECTION_UUIDS/')).read_bytes()
        else:
            content[name]=b'local release fixture\n'
    if alter:alter(content)
    checks=''.join(f'{hashlib.sha256(b).hexdigest()}  {k}\n' for k,b in sorted(content.items()))
    content['SHA256SUMS.txt']=checks.encode()
    with zipfile.ZipFile(p,'w') as z:
        for name,blob in sorted(content.items()):z.writestr(name,blob)
    return p

def test_package_has_real_profile(tmp_path):
    assert check(local_zip(tmp_path),repository_root=ROOT)['profile']=='G9.10'

@pytest.mark.parametrize('missing',[
 'STAGE1_SECTION_UUIDS/validation/profiles/G9.10.yaml',
 'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae09/investigate.py',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/test_ae09_investigation.py'])
def test_missing_critical_members_fail(tmp_path,missing):
    p=local_zip(tmp_path,lambda d:d.pop(missing))
    with pytest.raises(ValueError):check(p,repository_root=ROOT)


def test_corrupt_file_fails(tmp_path):
    p=local_zip(tmp_path)
    with zipfile.ZipFile(p) as z:data={n:z.read(n) for n in z.namelist()}
    name='STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae09/investigate.py'
    data[name]=b'BROKEN'
    with zipfile.ZipFile(p,'w') as z:
        for n,b in data.items():z.writestr(n,b)
    with pytest.raises(ValueError):check(p,repository_root=ROOT)

@pytest.mark.parametrize('badname',['../etc/passwd','STAGE1_SECTION_UUIDS/tests/__pycache__/secret.pyc','/absolute.txt'])
def test_unsafe_member_fails(tmp_path,badname):
    p=local_zip(tmp_path)
    with zipfile.ZipFile(p,'a') as z:z.writestr(badname,b'x')
    with pytest.raises(ValueError):check(p,repository_root=ROOT)


def test_invalid_referenced_tests_fail(tmp_path):
    def edit(data):
        k='STAGE1_SECTION_UUIDS/validation/profiles/G9.10.yaml'
        data[k]=data[k].replace(b'tests/semantic_audit/test_ae09_release.py',b'tests/unknown/missing_module.py')
    with pytest.raises(ValueError):check(local_zip(tmp_path,edit),repository_root=ROOT)


def test_compiled_python_member_rejected(tmp_path):
    p=local_zip(tmp_path)
    with zipfile.ZipFile(p,'a') as z:z.writestr('STAGE1_SECTION_UUIDS/audit_engine/__pycache__/x.pyc',b'')
    with pytest.raises(ValueError):check(p,repository_root=ROOT)
