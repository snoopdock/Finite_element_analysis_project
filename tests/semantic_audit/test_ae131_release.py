"""Independent negative controls for cumulative patch archive admission."""
import hashlib
import importlib.util
import zipfile
from pathlib import Path

import pytest

CHECKER=Path(__file__).parents[2] / 'tools' / 'check_ae131_patch.py'


def _checker():
    spec=importlib.util.spec_from_file_location('ae131_patch_checker',CHECKER)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _archive(tmp_path, extra=None, broken=None):
    checker=_checker()
    values={n: (b'id: G9.15\nregression:\ntest_ae131_protected_contracts.py' if n.endswith('G9.15.yaml') else b'safe') for n in checker.FILES if n!='SHA256SUMS.txt'}
    if broken:
        values[broken]=b'altered'
    lines=[hashlib.sha256(val).hexdigest()+'  '+name for name,val in sorted(values.items())]
    values['SHA256SUMS.txt']=('\n'.join(lines)+'\n').encode()
    path=tmp_path/'patch.zip'
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,payload in sorted(values.items()):
            z.writestr(name,payload)
        if extra:
            z.writestr(extra,b'evil')
    return path


def test_valid_fixture_accepted(tmp_path):
    _checker().validate(_archive(tmp_path))


@pytest.mark.parametrize('bad', ['../x','STAGE1_SECTION_UUIDS/../evil','/absolute','STAGE1_SECTION_UUIDS/evil\\nested','duplicate/../directory/'])
def test_unsafe_entries_rejected(tmp_path,bad):
    with pytest.raises(ValueError):
        _checker().validate(_archive(tmp_path,extra=bad))


def test_extra_regular_file_rejected(tmp_path):
    with pytest.raises(ValueError,match='member count'):
        _checker().validate(_archive(tmp_path,extra='extra.txt'))


def test_modification_after_manifest_generation_rejected(tmp_path):
    # Modify a member while retaining the original manifest.
    path=_archive(tmp_path)
    with zipfile.ZipFile(path) as z:
        data={n:z.read(n) for n in z.namelist()}
    data['README.md']=b'tampered'
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for n,b in data.items():z.writestr(n,b)
    with pytest.raises(ValueError,match='digest mismatch'):
        _checker().validate(path)
