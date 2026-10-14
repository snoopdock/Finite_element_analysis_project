"""Negative ZIP release-gate tests, including missing G9.6 and checksum tampering."""
from __future__ import annotations
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED, ZipInfo
import hashlib
import pytest
from tools.ae05_release_check import check, REQUIRED, DOCUMENTS, PROFILE, _profile_paths

ROOT = Path(__file__).resolve().parents[2]


def fake_package(tmp_path, *, omit=None, corrupt=None, pyc=False, duplicate=False,
                 bad_profile=None, symlink=False):
    package=tmp_path/'candidate.zip'
    files={}
    for member in sorted(REQUIRED):
        source=ROOT/member.removeprefix('STAGE1_SECTION_UUIDS/')
        files[member]=source.read_bytes()
    for name in DOCUMENTS:
        files[name]=b'AE-05 release test document\n'
    if omit: files.pop(omit)
    if bad_profile is not None: files[PROFILE]=bad_profile
    if pyc: files['STAGE1_SECTION_UUIDS/ae05/__pycache__/bad.pyc']=b'compiled'
    if symlink: files['STAGE1_SECTION_UUIDS/secret_link.py']=b'/tmp/secret'
    checksums=''.join(f'{hashlib.sha256(payload).hexdigest()}  {name}\n'
                       for name,payload in sorted(files.items()))
    files['SHA256SUMS.txt']=checksums.encode()
    with ZipFile(package,'w',ZIP_DEFLATED) as z:
        for name,payload in sorted(files.items()):
            if corrupt==name: payload=b'payload changed after hashing'
            if symlink and name.endswith('secret_link.py'):
                zi=ZipInfo(name);zi.create_system=3;zi.external_attr=(0o120777 << 16)
                z.writestr(zi,payload)
            else: z.writestr(name,payload)
        if duplicate:z.writestr(PROFILE,files[PROFILE])
    return package


def test_g95_profile_targets_are_present():
    targets=_profile_paths((ROOT/'validation/profiles/G9.6.yaml').read_bytes())
    assert len(targets)>=9
    assert all((ROOT/target).is_file() for target in targets)


def test_control_zip_passes(tmp_path):
    r=check(fake_package(tmp_path),ROOT)
    assert r['profile']=='G9.6'
    assert r['checksum_status']=='passed'


@pytest.mark.parametrize('bad', [PROFILE, 'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae05/service.py'])
def test_missing_files_rejected(tmp_path,bad):
    with pytest.raises(ValueError,match='Missing'):
        check(fake_package(tmp_path,omit=bad),ROOT)


def test_corrupted_payload_rejected(tmp_path):
    with pytest.raises(ValueError,match='checksum'):
        check(fake_package(tmp_path,corrupt=PROFILE),ROOT)


def test_compiled_bytecode_rejected(tmp_path):
    with pytest.raises(ValueError,match='Compiled'):
        check(fake_package(tmp_path,pyc=True),ROOT)


def test_duplicate_archive_name_rejected(tmp_path):
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',UserWarning)
        archive=fake_package(tmp_path,duplicate=True)
    with pytest.raises(ValueError,match='Duplicate ZIP'):
        check(archive,ROOT)


def test_symlink_zip_member_rejected(tmp_path):
    with pytest.raises(ValueError,match='symlink'):
        check(fake_package(tmp_path,symlink=True),ROOT)


def test_wrong_profile_id_rejected(tmp_path):
    raw=(ROOT/'validation/profiles/G9.6.yaml').read_bytes().replace(b'id: G9.6',b'id: G9.4')
    with pytest.raises(ValueError,match='ID mismatch'):
        check(fake_package(tmp_path,bad_profile=raw),ROOT)


def test_unknown_target_rejected():
    raw=b'id: G9.6\ntarget_tests:\n  - tests/unknown.py\nregression:\n  enabled: true\n  path: tests/\n'
    with pytest.raises(ValueError,match='inadequate'):
        _profile_paths(raw)
