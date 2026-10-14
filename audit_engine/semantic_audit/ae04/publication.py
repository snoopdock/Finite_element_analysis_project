"""Transactional, content-addressed publication for independently verified AE-04 campaigns.

The pointer is set to 'running' before an attempt and 'failed' on exception;
only a completed, verified generation can become the current publication.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import shutil
import tempfile
from audit_engine.semantic_audit.ae01.publication import canonical, sha, _atomic_bytes, _no_symlink_components, _fsync_dir
from .service import verify_campaign


def _read(path: Path) -> dict:
    _no_symlink_components(path)
    return json.loads(path.read_bytes())


def publish_campaign(record: dict, output: Path | str, *, before_output: Path | str,
                     after_output: Path | str, mutation_root: Path | None = None,
                     replay_mutation: bool = False) -> dict:
    """Publish only a reverified record, with atomic directory and latest pointer."""
    output = Path(os.path.abspath(output))
    _no_symlink_components(output)
    output.mkdir(parents=True, exist_ok=True)
    _no_symlink_components(output)
    # Audit source and publication roots must not overlap (including parent-child).
    for source in (before_output, after_output, mutation_root):
        if source is None: continue
        src = Path(source).resolve()
        if src == output or src in output.parents or output in src.parents:
            raise ValueError('Campaign publication overlaps an evidence/source root')
    lock = output / '.ae04.lock'
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        _atomic_bytes(output / 'LATEST.json', canonical({'status': 'running', 'generation': None}))
        try:
            verify_campaign(record, before_output, after_output,
                            mutation_root=mutation_root, replay_mutation=replay_mutation)
            rid = 'ae04-' + record['campaign_sha256'][:32]
            root = output / 'generations'
            root.mkdir(exist_ok=True)
            _no_symlink_components(root)
            dest = root / rid
            report = canonical(record)
            seal = canonical({'schema': 'ae04/artifact_seal/v1', 'generation': rid,
                              'artifacts': {'campaign.json': sha(report)}})
            if dest.exists():
                _no_symlink_components(dest)
                if not dest.is_dir() or {p.name for p in dest.iterdir()} != {'campaign.json','SEAL.json'}:
                    raise ValueError('Prior publication directory membership mismatch')
                _no_symlink_components(dest / 'campaign.json')
                _no_symlink_components(dest / 'SEAL.json')
                if (dest / 'campaign.json').read_bytes() != report or (dest / 'SEAL.json').read_bytes() != seal:
                    raise ValueError('Content-addressed generation collision or tampering')
            else:
                stage = Path(tempfile.mkdtemp(prefix='.ae04-stage-', dir=root))
                try:
                    _atomic_bytes(stage / 'campaign.json', report)
                    _atomic_bytes(stage / 'SEAL.json', seal)
                    os.replace(stage, dest)
                    _fsync_dir(root)
                finally:
                    if stage.exists(): shutil.rmtree(stage)
            _atomic_bytes(output / 'LATEST.json', canonical({
                'status': 'completed', 'generation': rid, 'seal_sha256': sha(seal)}))
            return {'generation': rid, 'seal_sha256': sha(seal), 'campaign_sha256': record['campaign_sha256']}
        except BaseException as error:
            _atomic_bytes(output / 'LATEST.json', canonical({'status': 'failed', 'generation': None,
                          'error_type': type(error).__name__}))
            raise
    finally:
        os.close(fd)


def verify_publication(output: Path | str, *, before_output: Path | str,
                       after_output: Path | str, mutation_root: Path | None = None,
                       replay_mutation: bool = False) -> dict:
    output = Path(os.path.abspath(output))
    _no_symlink_components(output)
    latest = _read(output / 'LATEST.json')
    if latest.get('status') != 'completed':
        raise ValueError('Latest campaign attempt is not completed')
    rid = latest.get('generation')
    if not isinstance(rid, str) or len(rid) != 37 or not rid.startswith('ae04-') or any(c not in '0123456789abcdef' for c in rid[5:]):
        raise ValueError('Unsafe or malformed campaign generation ID')
    folder = output / 'generations' / rid
    _no_symlink_components(folder)
    if not folder.is_dir() or {p.name for p in folder.iterdir()} != {'campaign.json','SEAL.json'}:
        raise ValueError('Missing or unexpected campaign generation artifacts')
    _no_symlink_components(folder / 'SEAL.json')
    _no_symlink_components(folder / 'campaign.json')
    seal_bytes = (folder / 'SEAL.json').read_bytes()
    if sha(seal_bytes) != latest.get('seal_sha256'):
        raise ValueError('Published seal does not match current pointer')
    seal = json.loads(seal_bytes)
    if seal.get('schema') != 'ae04/artifact_seal/v1' or seal.get('generation') != rid or set(seal['artifacts']) != {'campaign.json'}:
        raise ValueError('Invalid campaign artifact seal')
    data = (folder / 'campaign.json').read_bytes()
    if sha(data) != seal['artifacts']['campaign.json']:
        raise ValueError('Published campaign bytes do not match seal')
    record = json.loads(data)
    if rid != 'ae04-' + record.get('campaign_sha256','')[:32]:
        raise ValueError('Campaign publication identity mismatch')
    receipt = verify_campaign(record, before_output, after_output,
                              mutation_root=mutation_root, replay_mutation=replay_mutation)
    return {**receipt, 'generation': rid, 'seal_sha256': sha(seal_bytes)}
