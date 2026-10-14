"""Release checker negative controls: a missing G9.3 cannot pass the gate."""
from __future__ import annotations
import hashlib
from pathlib import Path
import zipfile

import pytest

from tools.check_ae021_patch import REQUIRED, check_package

ROOT=Path(__file__).resolve().parents[2]


def make_zip(tmp_path, *, omitted=(), mutated=None, extra=None):
    mutated=mutated or {}
    files={}
    for name in REQUIRED:
        if name=='SHA256SUMS.txt' or name in omitted:
            continue
        if name.startswith('STAGE1_SECTION_UUIDS/'):
            path=ROOT/name.removeprefix('STAGE1_SECTION_UUIDS/')
            files[name]=path.read_bytes()
        else:
            files[name]=b'# Release check synthetic fixture\n'
    files.update(mutated)
    if extra:
        files.update(extra)
    checksums=''.join(f'{hashlib.sha256(payload).hexdigest()}  {name}\n'
                      for name,payload in sorted(files.items()))
    files['SHA256SUMS.txt']=checksums.encode()
    p=tmp_path/'patch.zip'
    with zipfile.ZipFile(p,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,data in sorted(files.items()): z.writestr(name,data)
    return p


def test_valid_synthetic_package_satisfies_all_checkpoints(tmp_path):
    p=make_zip(tmp_path)
    assert check_package(p,ROOT)==[]


def test_profile_omission_is_release_failure(tmp_path):
    p=make_zip(tmp_path,omitted={'STAGE1_SECTION_UUIDS/validation/profiles/G9.3.yaml'})
    assert any('Missing required member' in e for e in check_package(p,ROOT))


def test_missing_impact_module_is_release_failure(tmp_path):
    p=make_zip(tmp_path,omitted={'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae02/impact.py'})
    assert any('impact.py' in e for e in check_package(p,ROOT))


def test_checksum_mutation_is_release_failure(tmp_path):
    p=make_zip(tmp_path)
    with zipfile.ZipFile(p,'a') as z:
        z.writestr('PATCH_MAP.md', b'counterfeit map')
    issues=check_package(p,ROOT)
    assert any('Duplicate' in e for e in issues)
    assert any('Checksum mismatch' in e for e in issues)


def test_compiled_file_is_forbidden_even_with_valid_checksums(tmp_path):
    p=make_zip(tmp_path,extra={'STAGE1_SECTION_UUIDS/tests/__pycache__/abc.pyc':b'bytes'})
    assert any('Compiled artifact' in e for e in check_package(p,ROOT))


def test_unsafe_traversal_member_is_forbidden(tmp_path):
    p=make_zip(tmp_path,extra={'STAGE1_SECTION_UUIDS/../escape.txt':b'escape'})
    assert any('Unsafe ZIP path' in e for e in check_package(p,ROOT))


def test_profile_target_missing_fails(tmp_path):
    profile=(ROOT/'validation/profiles/G9.3.yaml').read_text().replace(
        'tests/semantic_audit/test_ae021_impact.py', 'tests/semantic_audit/nonexistent.py')
    p=make_zip(tmp_path,mutated={'STAGE1_SECTION_UUIDS/validation/profiles/G9.3.yaml':profile.encode()})
    assert any('Target test absent' in e for e in check_package(p,ROOT))


def test_profile_id_mismatch_fails(tmp_path):
    profile=(ROOT/'validation/profiles/G9.3.yaml').read_text().replace('id: G9.3','id: G9.2')
    p=make_zip(tmp_path,mutated={'STAGE1_SECTION_UUIDS/validation/profiles/G9.3.yaml':profile.encode()})
    assert any('Profile ID mismatch' in e for e in check_package(p,ROOT))
