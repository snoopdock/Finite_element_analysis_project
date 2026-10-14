"""Release acceptance tests: essential packaging mistakes fail before upload."""
from __future__ import annotations
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import pytest
from tools.ae03_release_check import check, _profile_paths

ROOT = Path(__file__).resolve().parents[2]


def test_g94_exists_and_target_files_are_real():
    p = ROOT / 'validation/profiles/G9.4.yaml'
    assert p.is_file()
    targets = _profile_paths(p.read_bytes())
    assert len(targets) >= 7
    assert all((ROOT / path).is_file() for path in targets)


def build_fake_archive(tmp_path, *, omit_profile=False, corrupt=False, pyc=False):
    p = tmp_path / 'release.zip'
    files = {
      'STAGE1_SECTION_UUIDS/validation/profiles/G9.4.yaml': (ROOT / 'validation/profiles/G9.4.yaml').read_bytes(),
    }
    from tools.ae03_release_check import REQUIRED
    for name in REQUIRED:
        if name == 'STAGE1_SECTION_UUIDS/validation/profiles/G9.4.yaml':
            continue
        files[name] = (ROOT / name.removeprefix('STAGE1_SECTION_UUIDS/')).read_bytes()
    if omit_profile:
        del files['STAGE1_SECTION_UUIDS/validation/profiles/G9.4.yaml']
    if pyc:
        files['STAGE1_SECTION_UUIDS/pkg/__pycache__/x.pyc'] = b'fake'
    import hashlib
    manifest = ''.join(f'{hashlib.sha256(raw).hexdigest()}  {name}\n' for name, raw in sorted(files.items()))
    files['SHA256SUMS.txt'] = manifest.encode('ascii')
    with ZipFile(p, 'w', compression=ZIP_DEFLATED) as z:
        for name, raw in sorted(files.items()):
            if corrupt and name.endswith('source.py'):
                raw = b'changed after digest'
            z.writestr(name, raw)
    return p


def test_control_release_accepts_complete_profile(tmp_path):
    result = check(build_fake_archive(tmp_path), ROOT)
    assert result['profile'] == 'G9.4'
    assert result['checksum_status'] == 'passed'


def test_missing_profile_fails(tmp_path):
    with pytest.raises(ValueError, match='Missing'):
        check(build_fake_archive(tmp_path, omit_profile=True), ROOT)


def test_corrupted_payload_fails(tmp_path):
    with pytest.raises(ValueError, match='checksum'):
        check(build_fake_archive(tmp_path, corrupt=True), ROOT)


def test_compiled_python_payload_fails(tmp_path):
    with pytest.raises(ValueError, match='Compiled'):
        check(build_fake_archive(tmp_path, pyc=True), ROOT)


def test_unsafe_missing_target_rejected():
    profile = b'id: G9.4\ntarget_tests:\n  - tests/missing_not_real.py\nregression:\n  enabled: true\n'
    with pytest.raises(ValueError, match='adversarial'):
        _profile_paths(profile)


def test_profile_id_mismatch_rejected():
    raw = (ROOT / 'validation/profiles/G9.4.yaml').read_bytes().replace(b'id: G9.4', b'id: G9.3')
    with pytest.raises(ValueError, match='ID mismatch'):
        _profile_paths(raw)
