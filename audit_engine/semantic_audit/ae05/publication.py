"""Crash-aware append-only generation journal for AE-05; no implicit approvals.

The latest pointer is invalidated before every attempt, protected by an exclusive
file lock, and only promoted after detached re-verification. Prior generations
remain immutable; they are historical evidence, not the current decision.
"""
from __future__ import annotations
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import shutil
import tempfile

from audit_engine.semantic_audit.ae01.publication import (
    _atomic_bytes, _fsync_dir, _no_symlink_components, canonical, sha)
from .service import start_review, append_event, verify_review


def _path(path: Path | str) -> Path:
    out = Path(os.path.abspath(path))
    _no_symlink_components(out)
    return out


def _boundaries(output: Path, *sources: Path | str | None) -> None:
    for source in sources:
        if source is None:
            continue
        root = _path(source)
        if root == output or root in output.parents or output in root.parents:
            raise ValueError('AE-05 publication overlaps audit evidence/source root')


@contextmanager
def _exclusive(output: Path):
    _no_symlink_components(output)
    output.mkdir(parents=True, exist_ok=True)
    _no_symlink_components(output)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(output / '.ae05.lock', flags, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _latest(output: Path) -> dict:
    path = output / 'LATEST.json'
    _no_symlink_components(path)
    return json.loads(path.read_bytes())


def _stored(output: Path) -> dict:
    latest = _latest(output)
    rid = latest.get('generation')
    if latest.get('status') != 'completed' or not isinstance(rid, str) or not rid.startswith('ae05-') or (
        len(rid) != 37 or any(ch not in '0123456789abcdef' for ch in rid[5:])):
        raise ValueError('Latest review attempt is incomplete or invalid')
    folder = output / 'generations' / rid
    _no_symlink_components(folder)
    if not folder.is_dir() or {p.name for p in folder.iterdir()} != {'review.json','SEAL.json'}:
        raise ValueError('Review generation membership is unexpected')
    a, b = folder / 'review.json', folder / 'SEAL.json'
    _no_symlink_components(a); _no_symlink_components(b)
    seal_bytes, review_bytes = b.read_bytes(), a.read_bytes()
    if sha(seal_bytes) != latest.get('seal_sha256'):
        raise ValueError('Latest review seal digest differs')
    seal = json.loads(seal_bytes)
    if (seal.get('schema') != 'ae05/publication/v1' or seal.get('generation') != rid or
            seal.get('artifacts') != {'review.json': sha(review_bytes)}):
        raise ValueError('Review evidence does not match sealed artifact list')
    record = json.loads(review_bytes)
    if rid != 'ae05-'+record.get('review_sha256','')[:32]:
        raise ValueError('Review generation digest/identity mismatch')
    return record


def _commit(record: dict, output: Path, before: Path | str, after: Path | str,
            campaign: Path | str, *, mutation_root: Path | None, replay_mutation: bool) -> dict:
    # This function runs only under _exclusive.
    _atomic_bytes(output / 'LATEST.json', canonical({'status':'running','generation':None}))
    try:
        verify_review(record, campaign, before, after, mutation_root=mutation_root,
                      replay_mutation=replay_mutation)
        rid = 'ae05-'+record['review_sha256'][:32]
        root = output / 'generations'
        _no_symlink_components(root)
        root.mkdir(exist_ok=True)
        data = canonical(record)
        seal_bytes = canonical({'schema': 'ae05/publication/v1', 'generation': rid,
                                'artifacts': {'review.json': sha(data)}})
        dest = root / rid
        if dest.exists():
            _no_symlink_components(dest)
            if not dest.is_dir() or {p.name for p in dest.iterdir()} != {'review.json','SEAL.json'}:
                raise ValueError('Existing review generation is incomplete or replaced')
            _no_symlink_components(dest/'review.json'); _no_symlink_components(dest/'SEAL.json')
            if (dest/'review.json').read_bytes() != data or (dest/'SEAL.json').read_bytes() != seal_bytes:
                raise ValueError('Content-addressed review collision / evidence tampering')
        else:
            stage = Path(tempfile.mkdtemp(prefix='.ae05-stage-', dir=root))
            try:
                _atomic_bytes(stage/'review.json', data)
                _atomic_bytes(stage/'SEAL.json', seal_bytes)
                os.replace(stage, dest)
                _fsync_dir(root)
            finally:
                if stage.exists(): shutil.rmtree(stage)
        _atomic_bytes(output/'LATEST.json', canonical({
            'status':'completed', 'generation':rid, 'seal_sha256': sha(seal_bytes)}))
        return {'generation': rid, 'review_sha256':record['review_sha256'],
                'seal_sha256':sha(seal_bytes), 'review_state':record['state']['status']}
    except BaseException as error:
        _atomic_bytes(output/'LATEST.json', canonical({'status':'failed','generation':None,
                                                       'error_type':type(error).__name__}))
        raise


def initialize_review(output: Path | str, *, campaign_output: Path | str,
                      before_output: Path | str, after_output: Path | str,
                      mutation_root: Path | None = None, replay_mutation: bool = False) -> dict:
    out = _path(output)
    _boundaries(out, campaign_output, before_output, after_output, mutation_root)
    with _exclusive(out):
        if (out/'LATEST.json').exists() or (out/'generations').exists():
            raise ValueError('Review already initialized; use append_review, never reset history')
        packet = start_review(campaign_output, before_output, after_output,
                              mutation_root=mutation_root, replay_mutation=replay_mutation)
        return _commit(packet, out, before_output, after_output, campaign_output,
                       mutation_root=mutation_root, replay_mutation=replay_mutation)


def append_review(output: Path | str, *, campaign_output: Path | str,
                  before_output: Path | str, after_output: Path | str,
                  obligation_id: str, action: str, actor: str, note: str,
                  evidence_refs: list[str] | None = None,
                  mutation_root: Path | None = None, replay_mutation: bool = False) -> dict:
    out = _path(output)
    _boundaries(out, campaign_output, before_output, after_output, mutation_root)
    with _exclusive(out):
        # Serialized read-modify-write under the same lock prevents lost review events.
        current = _stored(out)
        verify_review(current, campaign_output, before_output, after_output,
                      mutation_root=mutation_root, replay_mutation=replay_mutation)
        updated = append_event(current, obligation_id, action, actor, note,
                               evidence_refs=evidence_refs)
        return _commit(updated, out, before_output, after_output, campaign_output,
                       mutation_root=mutation_root, replay_mutation=replay_mutation)


def verify_review_publication(output: Path | str, *, campaign_output: Path | str,
                              before_output: Path | str, after_output: Path | str,
                              mutation_root: Path | None = None, replay_mutation: bool = False) -> dict:
    out = _path(output)
    _boundaries(out, campaign_output, before_output, after_output, mutation_root)
    record = _stored(out)
    verification = verify_review(record, campaign_output, before_output, after_output,
                                 mutation_root=mutation_root, replay_mutation=replay_mutation)
    return {**verification, 'review_state': record['state'],
            'obligations': record['packet']['obligations']}
