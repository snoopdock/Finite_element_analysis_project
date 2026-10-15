"""Independent release-package negative controls for G9.16."""
import hashlib
import importlib.util
import stat
import zipfile
from pathlib import Path

import pytest

CHECKER=Path(__file__).parents[2] / 'tools/check_ae14_patch.py'


def checker():
    spec=importlib.util.spec_from_file_location('ae14_release_checker',CHECKER)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_archive(tmp_path, extra=None, alter=None, link=False):
    files={name: (b'id: G9.16\ntest_ae14_lexical_semantics.py\ntest_ae131_protected_contracts.py\nregression:\n' if name.endswith('G9.16.yaml') else b'test evidence')
           for name in checker().FILES if name!='SHA256SUMS.txt'}
    lines=[hashlib.sha256(data).hexdigest()+'  '+name for name,data in sorted(files.items())]
    files['SHA256SUMS.txt']=('\n'.join(lines)+'\n').encode()
    if alter:
        files[alter]=b'modified after hashing'
    path=tmp_path/'test.zip'
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,payload in sorted(files.items()):
            if link and name=='README.md':
                info=zipfile.ZipInfo(name)
                info.external_attr=(stat.S_IFLNK|0o777)<<16
                z.writestr(info,b'../../outside')
            else:
                z.writestr(name,payload)
        if extra:
            z.writestr(extra,b'bad')
    return path


def test_valid_fixture(tmp_path):
    checker().validate(make_archive(tmp_path))


@pytest.mark.parametrize('path',['../evil.py','STAGE1_SECTION_UUIDS/../x','/absolute','STAGE1_SECTION_UUIDS/evil\\part','STAGE1_SECTION_UUIDS/../../folder/'])
def test_unsafe_added_member(tmp_path,path):
    with pytest.raises(ValueError):
        checker().validate(make_archive(tmp_path,extra=path))


def test_modified_member_rejected(tmp_path):
    with pytest.raises(ValueError,match='Checksum'):
        checker().validate(make_archive(tmp_path,alter='README.md'))


def test_symlink_file_rejected(tmp_path):
    with pytest.raises(ValueError,match='Nonregular'):
        checker().validate(make_archive(tmp_path,link=True))
