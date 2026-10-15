"""Negative release tests: the artifact itself must enforce contract and mapping."""
import hashlib
from pathlib import Path
import zipfile
import pytest
import yaml
from tools.ae08_release_check import check, REQUIRED, PREFIX, PROFILE

REPO=Path(__file__).resolve().parents[2]


def package(tmp_path, remove=(), replace=None, extra=None, corrupt=None):
    replace=replace or {};extra=extra or {}
    members={}
    for path in REQUIRED-{'SHA256SUMS.txt'}:
        if path in remove:continue
        if path in replace:
            members[path]=replace[path]
        elif path.startswith(PREFIX):
            members[path]=(REPO/path[len(PREFIX):]).read_bytes()
        else:
            members[path]=b'AE08 documented local validation result\n'
    members.update(extra)
    checks=[]
    for path,data in sorted(members.items()):
        digest=hashlib.sha256(data).hexdigest()
        checks.append(f'{"0"*64 if path==corrupt else digest}  {path}')
    members['SHA256SUMS.txt']=('\n'.join(checks)+'\n').encode()
    path=tmp_path/'candidate.zip'
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,data in sorted(members.items()):z.writestr(name,data)
    return path


def test_valid_package_fixture(tmp_path):
    result=check(package(tmp_path),REPO)
    assert result['profile']=='G9.9' and result['fixture_hashes']=='verified'

@pytest.mark.parametrize('missing',[
    PROFILE,PREFIX+'audit_engine/semantic_audit/ae08/benchmark.py',
    PREFIX+'tests/fixtures/ae08_gold/gold.json',
    PREFIX+'tests/fixtures/ae08_gold/app.py',
    PREFIX+'tests/semantic_audit/test_ae08_benchmark.py',
    'LOCAL_VALIDATION_RESULTS.md'])
def test_missing_member_rejected(tmp_path,missing):
    with pytest.raises(ValueError,match='Required'):
        check(package(tmp_path,remove={missing}),REPO)


def test_invalid_checksum_rejected(tmp_path):
    with pytest.raises(ValueError,match='checksum'):
        check(package(tmp_path,corrupt=PREFIX+'audit_engine/semantic_audit/ae08/benchmark.py'),REPO)

@pytest.mark.parametrize('bad',['../outside.py','MAIN_BRANCH/.github/workflows/dispatcher.yml',
    PREFIX+'audit_engine/semantic_audit/ae08/__pycache__/cached.pyc'])
def test_unapproved_members_rejected(tmp_path,bad):
    with pytest.raises(ValueError):
        check(package(tmp_path,extra={bad:b'unapproved'}),REPO)


def test_registered_profile_cannot_point_to_missing_test(tmp_path):
    cfg=yaml.safe_load((REPO/'validation/profiles/G9.9.yaml').read_text())
    cfg['target_tests'].append('tests/this_test_is_not_in_repository.py')
    with pytest.raises(ValueError,match='Missing validation target'):
        check(package(tmp_path,replace={PROFILE:yaml.safe_dump(cfg).encode()}),REPO)


def test_required_ae08_tests_cannot_be_unselected(tmp_path):
    cfg=yaml.safe_load((REPO/'validation/profiles/G9.9.yaml').read_text())
    cfg['target_tests'].remove('tests/semantic_audit/test_ae08_benchmark.py')
    with pytest.raises(ValueError,match='does not select'):
        check(package(tmp_path,replace={PROFILE:yaml.safe_dump(cfg).encode()}),REPO)


def test_regression_cannot_be_disabled(tmp_path):
    cfg=yaml.safe_load((REPO/'validation/profiles/G9.9.yaml').read_text())
    cfg['regression']['enabled']=False
    with pytest.raises(ValueError,match='Invalid registered'):
        check(package(tmp_path,replace={PROFILE:yaml.safe_dump(cfg).encode()}),REPO)


def test_modified_fixture_labels_without_source_fingerprint_update_rejected(tmp_path):
    member=PREFIX+'tests/fixtures/ae08_gold/app.py'
    with pytest.raises(ValueError,match='Fixture label source checksum'):
        check(package(tmp_path,replace={member:b'import other\n'}),REPO)
