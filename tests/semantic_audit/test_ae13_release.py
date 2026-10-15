import hashlib
import io
import stat
import zipfile
from pathlib import Path
import pytest
from tools.check_ae13_patch import validate_bytes, REQUIRED, PREFIX

ROOT=Path(__file__).resolve().parents[2]


def make_zip(extra=None, drop=None, corrupt=False):
    data={}
    for path in REQUIRED-{'SHA256SUMS.txt'}:
        actual=ROOT/path.removeprefix(PREFIX) if path.startswith(PREFIX) else None
        data[path]=actual.read_bytes() if actual and actual.is_file() else b'placeholder'
    if drop:data.pop(drop,None)
    if extra:data.update(extra)
    if corrupt:data[PREFIX+'audit_engine/semantic_audit/ae13/identity.py']=b'tampered'
    sums=''.join(f'{hashlib.sha256(raw).hexdigest()}  {key}\n' for key,raw in sorted(data.items()))
    data['SHA256SUMS.txt']=sums.encode()
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,raw in data.items(): z.writestr(name,raw)
    return stream.getvalue()


def test_self_contained_release_gate_on_clean_archive():
    assert validate_bytes(make_zip(),repo_root=ROOT)['profile']=='G9.14'


@pytest.mark.parametrize('name',[
    '../outside.py', 'STAGE1_SECTION_UUIDS/../unsafe',
    'STAGE1_SECTION_UUIDS/../../evil', 'STAGE1_SECTION_UUIDS/bad\\path',
])
def test_release_rejects_extra_traversal_files(name):
    with pytest.raises(ValueError):validate_bytes(make_zip(extra={name:b'x'}),repo_root=ROOT)


def test_release_rejects_directory_traversal_even_with_manifest():
    # ZIP directory entries are rejected whether rehashed or not.
    blob=make_zip()
    stream=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(blob)) as z,zipfile.ZipFile(stream,'w') as out:
        for n in z.namelist():out.writestr(n,z.read(n))
        out.writestr('../bad/',b'')
    with pytest.raises(ValueError):validate_bytes(stream.getvalue(),repo_root=ROOT)


def test_release_rejects_symlink_member():
    blob=make_zip(); out=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(blob)) as z,zipfile.ZipFile(out,'w') as writer:
        for n in z.namelist():
            if n==PREFIX+'audit_engine/semantic_audit/ae13/identity.py':
                item=zipfile.ZipInfo(n);item.create_system=3;item.external_attr=(stat.S_IFLNK|0o777)<<16
                writer.writestr(item,b'target')
            else:writer.writestr(n,z.read(n))
    with pytest.raises(ValueError):validate_bytes(out.getvalue(),repo_root=ROOT)


def test_release_requires_profile():
    with pytest.raises(ValueError):validate_bytes(make_zip(drop=PREFIX+'validation/profiles/G9.14.yaml'),repo_root=ROOT)


def test_release_rejects_corrupted_digest():
    blob=make_zip();stream=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(blob)) as z,zipfile.ZipFile(stream,'w') as w:
        for n in z.namelist():w.writestr(n,(b'tamper' if n.endswith('identity.py') else z.read(n)))
    with pytest.raises(ValueError):validate_bytes(stream.getvalue(),repo_root=ROOT)


def test_release_checks_all_profile_targets_exist():
    root=ROOT.parent/'no-exists'
    with pytest.raises(ValueError,match='Missing test target'):
        validate_bytes(make_zip(),repo_root=root)
