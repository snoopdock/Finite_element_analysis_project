"""Adversarial tests for the exact-release AE-06 ZIP preflight validator."""
from __future__ import annotations
import hashlib
import io
from pathlib import Path
import stat
import zipfile
import pytest
import yaml

from tools.ae06_release_check import check, REQUIRED, DOCUMENTS, PROFILE, PREFIX

REPO=Path(__file__).resolve().parents[2]


def _archive(tmp_path, change=None):
    files={x:(REPO/x[len(PREFIX):]).read_bytes() for x in REQUIRED}
    files.update({x:b'Local release fixture\n' for x in DOCUMENTS})
    if change:change(files)
    checksums=''.join(f'{hashlib.sha256(files[x]).hexdigest()}  {x}\n' for x in sorted(files))
    files['SHA256SUMS.txt']=checksums.encode()
    out=tmp_path/'patch.zip'
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,blob in sorted(files.items()):z.writestr(name,blob)
    return out


def test_complete_profile_and_candidate_files_pass_release_gate(tmp_path):
    assert check(_archive(tmp_path),REPO)['profile']=='G9.7'


def test_missing_profile_rejected(tmp_path):
    p=_archive(tmp_path,lambda x:x.pop(PROFILE))
    with pytest.raises(ValueError,match='missing|Missing'):
        check(p,REPO)


def test_bad_yaml_profile_id_rejected(tmp_path):
    def mutation(files):
        files[PROFILE]=files[PROFILE].replace(b'id: G9.7',b'id: G9.6')
    with pytest.raises(ValueError,match='profile ID mismatch'):
        check(_archive(tmp_path,mutation),REPO)


def test_existing_test_path_must_be_present(tmp_path):
    def mutation(files):
        files[PROFILE]=files[PROFILE].replace(b'tests/ae01/test_vertical_slice.py',
                                              b'tests/ae01/missing_file.py')
    with pytest.raises(ValueError,match='target'):
        check(_archive(tmp_path,mutation),REPO)


def test_bad_checksum_is_rejected(tmp_path):
    out=_archive(tmp_path)
    with zipfile.ZipFile(out) as z:files={n:z.read(n) for n in z.namelist()}
    files[PREFIX+'audit_engine/semantic_audit/ae06/service.py']+=b'# unexpected\n'
    with zipfile.ZipFile(out,'w') as z:
        for n,v in files.items():z.writestr(n,v)
    with pytest.raises(ValueError,match='checksum'):
        check(out,REPO)


def test_compiled_file_is_rejected(tmp_path):
    out=_archive(tmp_path)
    with zipfile.ZipFile(out,'a') as z:z.writestr(PREFIX+'__pycache__/fake.pyc',b'x')
    with pytest.raises(ValueError,match='Compiled'):
        check(out,REPO)


def test_duplicate_member_is_rejected(tmp_path):
    out=_archive(tmp_path)
    with zipfile.ZipFile(out,'a') as z:z.writestr(PROFILE,b'bad')
    with pytest.raises(ValueError,match='Duplicate'):
        check(out,REPO)


def test_symlink_in_archive_is_rejected(tmp_path):
    out=_archive(tmp_path)
    member=zipfile.ZipInfo(PREFIX+'malicious')
    member.create_system=3
    member.external_attr=(stat.S_IFLNK | 0o777)<<16
    with zipfile.ZipFile(out,'a') as z:z.writestr(member,b'/tmp')
    with pytest.raises(ValueError,match='symlink'):
        check(out,REPO)


def test_path_traversal_in_archive_is_rejected(tmp_path):
    out=_archive(tmp_path)
    with zipfile.ZipFile(out,'a') as z:z.writestr('../escape',b'bad')
    with pytest.raises(ValueError,match='Unsafe'):
        check(out,REPO)
