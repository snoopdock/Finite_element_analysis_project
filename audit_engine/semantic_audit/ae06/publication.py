"""AE-06 transactional publication of independently rederived remediation assessments.

All authoritative inputs remain read-only; a failed attempt cannot expose a
previous successful assessment through LATEST. Historical generations are kept.
"""
from __future__ import annotations
import fcntl
import json
import os
from pathlib import Path
import shutil
import tempfile
from contextlib import contextmanager

from audit_engine.semantic_audit.ae01.publication import (
    canonical, sha, _atomic_bytes, _fsync_dir, _no_symlink_components)
from .service import verify_assessment


def _path(p: Path | str) -> Path:
    path = Path(os.path.abspath(p))
    _no_symlink_components(path)
    return path


def _safe_bounds(out: Path, kwargs: dict) -> None:
    for key in ('origin_before', 'flagged_output', 'current_output', 'origin_campaign',
                'origin_review', 'followup_campaign', 'origin_mutation_root',
                'followup_mutation_root'):
        source = kwargs.get(key)
        if source is None: continue
        root = _path(source)
        if root == out or root in out.parents or out in root.parents:
            raise ValueError(f'AE-06 output cannot overlap input evidence: {key}')
    for item in (*kwargs.get('history_outputs', ()), *kwargs.get('history_campaigns', ())):
        root = _path(item)
        if root == out or root in out.parents or out in root.parents:
            raise ValueError('AE-06 output overlaps historical evidence')


@contextmanager
def _locked(out: Path):
    _no_symlink_components(out)
    out.mkdir(parents=True, exist_ok=True)
    _no_symlink_components(out)
    fd = os.open(out/'.ae06.lock', os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _stored(out: Path) -> dict:
    latest_file = out/'LATEST.json'
    _no_symlink_components(latest_file)
    latest = json.loads(latest_file.read_bytes())
    name = latest.get('generation')
    if latest.get('status') != 'completed' or not isinstance(name,str) or not name.startswith('ae06-') or (
            len(name)!=37 or any(c not in '0123456789abcdef' for c in name[5:])):
        raise ValueError('AE-06 LATEST is incomplete or malformed')
    folder = out/'generations'/name
    _no_symlink_components(folder)
    if not folder.is_dir() or {p.name for p in folder.iterdir()} != {'assessment.json','SEAL.json'}:
        raise ValueError('Missing or unexpected AE-06 generation artifacts')
    a,b = folder/'assessment.json', folder/'SEAL.json'
    _no_symlink_components(a);_no_symlink_components(b)
    seal_bytes = b.read_bytes()
    if sha(seal_bytes) != latest.get('seal_sha256'):
        raise ValueError('AE-06 latest seal does not match content')
    seal = json.loads(seal_bytes)
    report_bytes = a.read_bytes()
    if seal != {'schema':'ae06/publication/v1', 'generation':name,
                'artifacts':{'assessment.json':sha(report_bytes)}}:
        raise ValueError('AE-06 artifact seal does not match content')
    record = json.loads(report_bytes)
    if sha(canonical(record)) != sha(report_bytes) or name != 'ae06-'+record.get('assessment_sha256','')[:32]:
        raise ValueError('AE-06 assessment is noncanonical or identity mismatched')
    return record


def publish_assessment(record: dict, output: Path | str, **inputs) -> dict:
    out = _path(output)
    _safe_bounds(out, inputs)
    with _locked(out):
        _atomic_bytes(out/'LATEST.json', canonical({'status':'running','generation':None}))
        try:
            verified = verify_assessment(record, **inputs)
            name = 'ae06-'+record['assessment_sha256'][:32]
            data = canonical(record)
            seal = canonical({'schema':'ae06/publication/v1','generation':name,
                              'artifacts':{'assessment.json':sha(data)}})
            generations = out/'generations'
            _no_symlink_components(generations)
            generations.mkdir(exist_ok=True)
            _no_symlink_components(generations)
            dest = generations/name
            if dest.exists() or dest.is_symlink():
                _no_symlink_components(dest)
                if not dest.is_dir() or {x.name for x in dest.iterdir()} != {'assessment.json','SEAL.json'}:
                    raise ValueError('Existing AE-06 generation is malformed')
                _no_symlink_components(dest/'assessment.json');_no_symlink_components(dest/'SEAL.json')
                if (dest/'assessment.json').read_bytes()!=data or (dest/'SEAL.json').read_bytes()!=seal:
                    raise ValueError('Previously published AE-06 generation was modified')
            else:
                stage = Path(tempfile.mkdtemp(prefix='.ae06-stage-',dir=generations))
                try:
                    _atomic_bytes(stage/'assessment.json',data)
                    _atomic_bytes(stage/'SEAL.json',seal)
                    os.replace(stage,dest)
                    _fsync_dir(generations)
                finally:
                    if stage.exists():shutil.rmtree(stage)
            # Self-test the final on-disk generation, before activating pointer.
            _atomic_bytes(out/'LATEST.json', canonical({'status':'completed','generation':name,
                                                       'seal_sha256':sha(seal)}))
            stored = _stored(out)
            if canonical(stored) != data:
                raise ValueError('Published assessment differs from verified input')
            return {'generation':name,'seal_sha256':sha(seal), **verified}
        except BaseException as error:
            _atomic_bytes(out/'LATEST.json',canonical({'status':'failed','generation':None,
                                                       'error_type':type(error).__name__}))
            raise


def verify_assessment_publication(output: Path | str, **inputs) -> dict:
    out = _path(output)
    _safe_bounds(out,inputs)
    record = _stored(out)
    return {'generation':'ae06-'+record['assessment_sha256'][:32],
            **verify_assessment(record, **inputs)}
