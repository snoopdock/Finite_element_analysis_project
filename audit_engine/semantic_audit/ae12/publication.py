"""Fail-closed, generation-atomic publication and independent AE-12 replay."""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import shutil
import tempfile
from audit_engine.semantic_audit.ae01.publication import (
    canonical, sha, _atomic_bytes, _fsync_dir, _no_symlink_components)
from .analyze import build_report, verify_report


def _safe(path: Path | str) -> Path:
    result=Path(os.path.abspath(path))
    _no_symlink_components(result)
    return result


def _boundary(output, sources):
    out=_safe(output)
    for item in sources:
        if item is None:
            continue
        p=_safe(item)
        if out==p or out in p.parents or p in out.parents:
            raise ValueError('Output overlaps source, evidence, policy or runtime log')
    return out


def _read(out:Path) -> dict:
    _no_symlink_components(out)
    latest_file=out/'LATEST.json'
    _no_symlink_components(latest_file)
    latest=json.loads(latest_file.read_bytes())
    gen=latest.get('generation')
    if (latest.get('status')!='completed' or not isinstance(gen,str) or
        len(gen)!=37 or not gen.startswith('ae12-') or
        any(c not in '0123456789abcdef' for c in gen[5:])):
        raise ValueError('AE-12 latest attempt not completed')
    folder=out/'generations'/gen
    _no_symlink_components(folder)
    if not folder.is_dir() or {p.name for p in folder.iterdir()} != {'report.json','SEAL.json'}:
        raise ValueError('AE-12 generation membership incomplete')
    rp,sp=folder/'report.json',folder/'SEAL.json'
    _no_symlink_components(rp)
    _no_symlink_components(sp)
    raw, seal=rp.read_bytes(),sp.read_bytes()
    if sha(seal)!=latest.get('seal_sha256'):
        raise ValueError('Latest pointer seal mismatch')
    if json.loads(seal)!={'schema':'ae12/seal/v1','generation':gen,'artifacts':{'report.json':sha(raw)}}:
        raise ValueError('Generation seal mismatch')
    report=json.loads(raw)
    if canonical(report)!=raw or not isinstance(report.get('record_sha256'),str):
        raise ValueError('Invalid canonical report')
    body={k:v for k,v in report.items() if k!='record_sha256'}
    if sha(canonical(body)) != report['record_sha256'] or gen!='ae12-'+report['record_sha256'][:32]:
        raise ValueError('Generation report identity mismatch')
    return report


def publish(ae01_output,source_root,policy_file,output,*,runtime_log=None,generation_id=None):
    out=_boundary(output,(ae01_output,source_root,policy_file,runtime_log))
    out.mkdir(parents=True,exist_ok=True)
    _no_symlink_components(out)
    fd=os.open(out/'.ae12.lock',os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX)
        _atomic_bytes(out/'LATEST.json',canonical({'status':'running','generation':None}))
        try:
            report=build_report(ae01_output,source_root,policy_file,
                                generation_id=generation_id,runtime_log=runtime_log)
            verify_report(report,ae01_output,source_root,policy_file,runtime_log=runtime_log)
            name='ae12-'+report['record_sha256'][:32]
            data=canonical(report)
            seal=canonical({'schema':'ae12/seal/v1','generation':name,
                            'artifacts':{'report.json':sha(data)}})
            gens=out/'generations'
            _no_symlink_components(gens)
            gens.mkdir(exist_ok=True)
            dest=gens/name
            payloads={'report.json':data,'SEAL.json':seal}
            if dest.exists() or dest.is_symlink():
                _no_symlink_components(dest)
                if not dest.is_dir() or {p.name for p in dest.iterdir()}!=set(payloads):
                    raise ValueError('Existing AE-12 generation is incompatible')
                for part,blob in payloads.items():
                    _no_symlink_components(dest/part)
                    if (dest/part).read_bytes()!=blob:
                        raise ValueError('Existing AE-12 generation was corrupted')
            else:
                stage=Path(tempfile.mkdtemp(prefix='.ae12-stage-',dir=gens))
                try:
                    for part,blob in payloads.items():
                        _atomic_bytes(stage/part,blob)
                    os.replace(stage,dest)
                    _fsync_dir(gens)
                finally:
                    if stage.exists():shutil.rmtree(stage)
            _atomic_bytes(out/'LATEST.json',canonical({'status':'completed','generation':name,
                                                     'seal_sha256':sha(seal)}))
            return verify_publication(out,ae01_output,source_root,policy_file,runtime_log=runtime_log)
        except BaseException as exc:
            _atomic_bytes(out/'LATEST.json',canonical({'status':'failed','generation':None,
                                                       'error_type':type(exc).__name__}))
            raise
    finally:
        fcntl.flock(fd,fcntl.LOCK_UN)
        os.close(fd)


def verify_publication(output,ae01_output,source_root,policy_file,*,runtime_log=None):
    out=_boundary(output,(ae01_output,source_root,policy_file,runtime_log))
    earlier=_read(out)
    verified=verify_report(earlier,ae01_output,source_root,policy_file,runtime_log=runtime_log)
    if canonical(_read(out))!=canonical(earlier):
        raise ValueError('Publication changed during verification')
    return verified
