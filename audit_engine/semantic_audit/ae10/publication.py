"""Atomic, content-addressed AE-10 publication and independent evidence replay."""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import shutil
import tempfile

from audit_engine.semantic_audit.ae01.publication import (canonical, sha, _atomic_bytes,
                                                          _fsync_dir, _no_symlink_components)
from .science import build_report, verify_report


def _safe(p):
    result=Path(os.path.abspath(p))
    _no_symlink_components(result)
    return result


def _check_roots(output, spec, root):
    out, src, data=map(_safe,(output,spec,root))
    for p in (src,data):
        if out==p or out in p.parents or p in out.parents:
            raise ValueError('Publication overlaps its source inputs')
    return out,src,data


def _read(out:Path):
    latest_file=out/'LATEST.json'
    _no_symlink_components(latest_file)
    latest=json.loads(latest_file.read_bytes())
    name=latest.get('generation')
    if (latest.get('status')!='completed' or not isinstance(name,str) or
        len(name)!=37 or not name.startswith('ae10-') or any(x not in '0123456789abcdef' for x in name[5:])):
        raise ValueError('AE-10 last attempt is not completed')
    gen=out/'generations'/name
    _no_symlink_components(gen)
    if not gen.is_dir() or {p.name for p in gen.iterdir()}!={'report.json','SEAL.json'}:
        raise ValueError('Malformed AE-10 generation')
    _no_symlink_components(gen/'report.json')
    _no_symlink_components(gen/'SEAL.json')
    report_bytes=(gen/'report.json').read_bytes()
    seal_bytes=(gen/'SEAL.json').read_bytes()
    if sha(seal_bytes)!=latest.get('seal_sha256'):
        raise ValueError('AE-10 pointer seal mismatch')
    if json.loads(seal_bytes)!={'schema':'ae10/seal/v1','generation':name,
                                  'artifacts':{'report.json':sha(report_bytes)}}:
        raise ValueError('AE-10 report seal mismatch')
    report=json.loads(report_bytes)
    if canonical(report)!=report_bytes or name!='ae10-'+report['record_sha256'][:32]:
        raise ValueError('AE-10 published report identity mismatch')
    return report


def publish_scientific_audit(spec_file, artifacts_root, output):
    out,spec,root=_check_roots(output,spec_file,artifacts_root)
    out.mkdir(parents=True,exist_ok=True)
    _no_symlink_components(out)
    fd=os.open(out/'.ae10.lock',os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        _atomic_bytes(out/'LATEST.json',canonical({'status':'running','generation':None}))
        try:
            record=build_report(spec,root)
            verify_report(record,spec,root)
            name='ae10-'+record['record_sha256'][:32]
            data=canonical(record)
            seal=canonical({'schema':'ae10/seal/v1','generation':name,
                            'artifacts':{'report.json':sha(data)}})
            gens=out/'generations'
            _no_symlink_components(gens)
            gens.mkdir(exist_ok=True)
            dest=gens/name
            blobs={'report.json':data,'SEAL.json':seal}
            if dest.exists() or dest.is_symlink():
                _no_symlink_components(dest)
                if not dest.is_dir() or {p.name for p in dest.iterdir()}!=set(blobs):
                    raise ValueError('Existing AE-10 generation has incompatible members')
                for member,contents in blobs.items():
                    _no_symlink_components(dest/member)
                    if (dest/member).read_bytes()!=contents:
                        raise ValueError('Existing AE-10 generation is corrupted')
            else:
                stage=Path(tempfile.mkdtemp(dir=gens,prefix='.ae10-stage-'))
                try:
                    for member,contents in blobs.items():
                        _atomic_bytes(stage/member,contents)
                    os.replace(stage,dest)
                    _fsync_dir(gens)
                finally:
                    if stage.exists():
                        shutil.rmtree(stage)
            _atomic_bytes(out/'LATEST.json',canonical({'status':'completed','generation':name,
                                                      'seal_sha256':sha(seal)}))
            return verify_publication(out,spec,root)
        except BaseException as exc:
            _atomic_bytes(out/'LATEST.json',canonical({'status':'failed','generation':None,
                                                       'error_type':type(exc).__name__}))
            raise
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def verify_publication(output, spec_file, artifacts_root):
    out,spec,root=_check_roots(output,spec_file,artifacts_root)
    before=_read(out)
    verified=verify_report(before,spec,root)
    if canonical(before)!=canonical(_read(out)):
        raise ValueError('AE-10 publication changed during verification')
    return verified
