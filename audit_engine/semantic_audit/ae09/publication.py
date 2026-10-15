"""Generation-atomic AE-09 publication; independent replay is mandatory for acceptance."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import shutil
import tempfile

from audit_engine.semantic_audit.ae01.publication import (
    canonical, sha, _atomic_bytes, _fsync_dir, _no_symlink_components)
from .investigate import build_report, verify_report


def _safe(path:Path|str)->Path:
    p=Path(os.path.abspath(path))
    _no_symlink_components(p)
    return p


def _bounds(out:Path, inputs:tuple[Path,...])->None:
    for p in inputs:
        p=_safe(p)
        if out==p or out in p.parents or p in out.parents:
            raise ValueError('Publication must not overlap evidence, source or log files')


@contextmanager
def _locked(out:Path):
    out.mkdir(parents=True,exist_ok=True)
    _no_symlink_components(out)
    fd=os.open(out/'.ae09.lock',os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd,fcntl.LOCK_UN)
        os.close(fd)


def _load(out:Path)->dict:
    _no_symlink_components(out)
    latest_path=out/'LATEST.json'
    _no_symlink_components(latest_path)
    latest=json.loads(latest_path.read_bytes())
    name=latest.get('generation')
    if (latest.get('status')!='completed' or not isinstance(name,str) or
        len(name)!=37 or not name.startswith('ae09-') or
        any(ch not in '0123456789abcdef' for ch in name[5:])):
        raise ValueError('AE-09 LATEST is incomplete, failed or malformed')
    folder=out/'generations'/name
    _no_symlink_components(folder)
    if not folder.is_dir() or {p.name for p in folder.iterdir()}!={'report.json','SEAL.json'}:
        raise ValueError('Missing or unexpected AE-09 generation members')
    report_file=folder/'report.json'
    seal_file=folder/'SEAL.json'
    _no_symlink_components(report_file)
    _no_symlink_components(seal_file)
    data=report_file.read_bytes()
    seal=seal_file.read_bytes()
    if sha(seal)!=latest.get('seal_sha256'):
        raise ValueError('AE-09 LATEST seal mismatch')
    if json.loads(seal)!={'schema':'ae09/seal/v1','generation':name,'artifacts':{'report.json':sha(data)}}:
        raise ValueError('AE-09 report seal mismatch')
    report=json.loads(data)
    if canonical(report)!=data:
        raise ValueError('Noncanonical AE-09 report')
    digest=report.get('record_sha256')
    if not isinstance(digest,str):
        raise ValueError('Missing report identity')
    body={k:v for k,v in report.items() if k!='record_sha256'}
    if sha(canonical(body))!=digest or name!='ae09-'+digest[:32]:
        raise ValueError('Report identity/contents disagree')
    return report


def publish_investigation(ae01_output:Path|str, log_file:Path|str, source_root:Path|str,
                          output:Path|str, *, generation_id:str|None=None,
                          max_depth:int=3, max_candidates:int=250) -> dict:
    out=_safe(output)
    _bounds(out,(Path(ae01_output),Path(log_file),Path(source_root)))
    with _locked(out):
        _atomic_bytes(out/'LATEST.json',canonical({'status':'running','generation':None}))
        try:
            record=build_report(ae01_output,log_file,source_root,generation_id=generation_id,
                                max_depth=max_depth,max_candidates=max_candidates)
            verify_report(record,ae01_output,log_file,source_root)
            name='ae09-'+record['record_sha256'][:32]
            data=canonical(record)
            seal=canonical({'schema':'ae09/seal/v1','generation':name,
                            'artifacts':{'report.json':sha(data)}})
            gens=out/'generations'
            _no_symlink_components(gens)
            gens.mkdir(exist_ok=True)
            dest=gens/name
            blobs={'report.json':data,'SEAL.json':seal}
            if dest.exists() or dest.is_symlink():
                _no_symlink_components(dest)
                if not dest.is_dir() or {p.name for p in dest.iterdir()}!=set(blobs):
                    raise ValueError('Existing AE-09 generation is malformed')
                for member,blob in blobs.items():
                    _no_symlink_components(dest/member)
                    if (dest/member).read_bytes()!=blob:
                        raise ValueError('Existing generation is corrupted')
            else:
                stage=Path(tempfile.mkdtemp(dir=gens,prefix='.ae09-stage-'))
                try:
                    for member,blob in blobs.items():
                        _atomic_bytes(stage/member,blob)
                    os.replace(stage,dest)
                    _fsync_dir(gens)
                finally:
                    if stage.exists():shutil.rmtree(stage)
            _atomic_bytes(out/'LATEST.json',canonical({'status':'completed','generation':name,'seal_sha256':sha(seal)}))
            verified=verify_publication(out,ae01_output,log_file,source_root)
            return {'generation':name,**verified}
        except BaseException as exc:
            _atomic_bytes(out/'LATEST.json',canonical({'status':'failed','generation':None,'error_type':type(exc).__name__}))
            raise


def verify_publication(output:Path|str,ae01_output:Path|str,log_file:Path|str,
                       source_root:Path|str)->dict:
    out=_safe(output)
    _bounds(out,(Path(ae01_output),Path(log_file),Path(source_root)))
    record=_load(out)
    result=verify_report(record,ae01_output,log_file,source_root)
    if canonical(_load(out))!=canonical(record):
        raise ValueError('AE-09 publication changed during detached verification')
    return result
