"""Release-test oracle: deliberately corrupted archives must fail the gate."""
from __future__ import annotations
import hashlib
from pathlib import Path
import zipfile
import pytest
import yaml
from tools.ae07_release_check import check, REQUIRED, PREFIX, PROFILE


def archive_fixture(tmp_path, repo, *, omitted=None, modified=None, extra=None,
                    corrupt_hash=None):
    omitted=omitted or set(); modified=modified or {}; extra=extra or {}
    data={}
    for name in REQUIRED-{'SHA256SUMS.txt'}:
        if name in omitted:continue
        if name in modified:
            data[name]=modified[name]
        elif name.startswith(PREFIX):
            data[name]=(repo/name[len(PREFIX):]).read_bytes()
        else:
            data[name]=b'AE-07 release documentation\n'
    data.update(extra)
    checks=[]
    for name in sorted(data):
        digest=hashlib.sha256(data[name]).hexdigest()
        if name==corrupt_hash:digest='0'*64
        checks.append(f'{digest}  {name}')
    data['SHA256SUMS.txt']=('\n'.join(checks)+'\n').encode()
    out=tmp_path/'patch.zip'
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as zip_file:
        for name,contents in sorted(data.items()):zip_file.writestr(name,contents)
    return out


@pytest.fixture
def repository():return Path(__file__).resolve().parents[2]


def test_well_formed_release_package_is_accepted(tmp_path,repository):
    receipt=check(archive_fixture(tmp_path,repository),repository)
    assert receipt['profile']=='G9.8'
    assert receipt['selected_tests']>=10
    assert receipt['checksums']=='verified'


@pytest.mark.parametrize('missing',[PROFILE,
    PREFIX+'audit_engine/semantic_audit/ae07/service.py',
    PREFIX+'tests/semantic_audit/test_ae07_portfolio.py',
    'LOCAL_VALIDATION_RESULTS.md'])
def test_missing_mandatory_member_is_rejected(tmp_path,repository,missing):
    with pytest.raises(ValueError,match='Required'):
        check(archive_fixture(tmp_path,repository,omitted={missing}),repository)


def test_corrupted_checksum_is_rejected(tmp_path,repository):
    member=PREFIX+'audit_engine/semantic_audit/ae07/service.py'
    with pytest.raises(ValueError,match='checksum'):
        check(archive_fixture(tmp_path,repository,corrupt_hash=member),repository)


@pytest.mark.parametrize('extra',[
    '../escape.txt','STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae07/__pycache__/module.pyc',
    'MAIN_BRANCH/.github/workflows/replacement.yaml', 'STAGE1_SECTION_UUIDS/stray.py'])
def test_unapproved_or_unsafe_file_is_rejected(tmp_path,repository,extra):
    with pytest.raises(ValueError):
        check(archive_fixture(tmp_path,repository,extra={extra:b'unapproved'}),repository)


def test_profile_pointing_to_missing_test_is_rejected(tmp_path,repository):
    p=yaml.safe_load((repository/'validation/profiles/G9.8.yaml').read_text())
    p['target_tests'].append('tests/this_missing_test.py')
    payload=yaml.safe_dump(p).encode()
    with pytest.raises(ValueError,match='Missing validation target'):
        check(archive_fixture(tmp_path,repository,modified={PROFILE:payload}),repository)


def test_profile_omits_new_ae07_test_rejected(tmp_path,repository):
    p=yaml.safe_load((repository/'validation/profiles/G9.8.yaml').read_text())
    p['target_tests'].remove('tests/semantic_audit/test_ae07_portfolio.py')
    with pytest.raises(ValueError,match='AE-07 tests'):
        check(archive_fixture(tmp_path,repository,modified={PROFILE:yaml.safe_dump(p).encode()}),repository)


def test_profile_disables_regression_rejected(tmp_path,repository):
    p=yaml.safe_load((repository/'validation/profiles/G9.8.yaml').read_text())
    p['regression']['enabled']=False
    with pytest.raises(ValueError,match='profile'):
        check(archive_fixture(tmp_path,repository,modified={PROFILE:yaml.safe_dump(p).encode()}),repository)


def test_traversal_in_profile_test_target_rejected(tmp_path,repository):
    p=yaml.safe_load((repository/'validation/profiles/G9.8.yaml').read_text())
    p['target_tests'].append('tests/../outside.py')
    with pytest.raises(ValueError,match='Invalid test target'):
        check(archive_fixture(tmp_path,repository,modified={PROFILE:yaml.safe_dump(p).encode()}),repository)
