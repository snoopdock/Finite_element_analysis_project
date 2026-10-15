"""Independent negative controls for G9.17 patch file admission."""
import hashlib
import importlib.util
import stat
import zipfile
from pathlib import Path

import pytest

CHECKER=Path(__file__).parents[2]/'tools/check_ae15_patch.py'


def checker():
    spec=importlib.util.spec_from_file_location('ae15_checker',CHECKER)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def archive(tmp_path, *, extra=None, replace=None, symlink=False):
    c=checker()
    content={name:(b'id: G9.17\ntest_ae15_flow.py\ntest_ae15_release.py\ntest_ae14_lexical_semantics.py\ntest_ae131_protected_contracts.py\nregression:\n'
                   if name.endswith('G9.17.yaml') else b'test fixture bytes')
             for name in c.FILES if name!='SHA256SUMS.txt'}
    checks='\n'.join(hashlib.sha256(b).hexdigest()+'  '+n for n,b in sorted(content.items()))+'\n'
    content['SHA256SUMS.txt']=checks.encode()
    if replace:content[replace]=b'modified without new digest'
    file=tmp_path/'fixture.zip'
    with zipfile.ZipFile(file,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,blob in sorted(content.items()):
            if symlink and name=='README.md':
                info=zipfile.ZipInfo(name)
                info.external_attr=(stat.S_IFLNK|0o777)<<16
                z.writestr(info,b'../../outside')
            else:z.writestr(name,blob)
        if extra:z.writestr(extra,b'malicious')
    return file


def test_valid_archive(tmp_path):checker().validate(archive(tmp_path))

@pytest.mark.parametrize('name',['../evil','STAGE1_SECTION_UUIDS/../escape','/absolute','folder\\malicious','STAGE1_SECTION_UUIDS/unexpected.txt','bad/dir/'])
def test_extra_members_rejected(tmp_path,name):
    with pytest.raises(ValueError):checker().validate(archive(tmp_path,extra=name))


def test_rehashed_content_mismatch_rejected(tmp_path):
    with pytest.raises(ValueError,match='Checksum'):checker().validate(archive(tmp_path,replace='README.md'))


def test_symlink_entry_rejected(tmp_path):
    with pytest.raises(ValueError,match='Nonregular'):checker().validate(archive(tmp_path,symlink=True))
