"""Transactional AE-07 publication and detached native-evidence replay.

LATEST is invalidated at the beginning of every attempt. A generation is only
published after independently reconstructing all inputs and SARIF projection.
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
    canonical, sha, _atomic_bytes, _fsync_dir, _no_symlink_components)
from .service import verify_portfolio, _validated_entries
from .sarif import render_sarif


def _path(p: Path | str) -> Path:
    path = Path(os.path.abspath(p))
    _no_symlink_components(path)
    return path


def _bounds(output: Path, entries: list[dict]) -> None:
    for row in _validated_entries(entries):
        paths = [row['assessment_output'], *[row['inputs'][field] for field in (
            'origin_before','flagged_output','current_output','origin_campaign',
            'origin_review','followup_campaign')],
                 *row['inputs']['history_outputs'], *row['inputs']['history_campaigns']]
        for field in ('origin_mutation_root','followup_mutation_root'):
            if row['inputs'][field] is not None:
                paths.append(row['inputs'][field])
        for path in paths:
            p = _path(path)
            if output == p or output in p.parents or p in output.parents:
                raise ValueError('AE-07 output overlaps authoritative source evidence')


@contextmanager
def _locked(out: Path):
    _no_symlink_components(out)
    out.mkdir(parents=True,exist_ok=True)
    _no_symlink_components(out)
    fd=os.open(out/'.ae07.lock',os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd,fcntl.LOCK_UN)
        os.close(fd)


def _stored(out: Path) -> tuple[dict,dict]:
    _no_symlink_components(out)
    latest_path=out/'LATEST.json'
    _no_symlink_components(latest_path)
    latest=json.loads(latest_path.read_bytes())
    name=latest.get('generation')
    if (latest.get('status')!='completed' or not isinstance(name,str) or
            not name.startswith('ae07-') or len(name)!=37 or
            any(ch not in '0123456789abcdef' for ch in name[5:])):
        raise ValueError('AE-07 LATEST is incomplete or malformed')
    directory=out/'generations'/name
    _no_symlink_components(directory)
    if not directory.is_dir() or {p.name for p in directory.iterdir()} != {'portfolio.json','results.sarif','SEAL.json'}:
        raise ValueError('AE-07 generation has missing or unexpected artifacts')
    for member in ('portfolio.json','results.sarif','SEAL.json'):
        _no_symlink_components(directory/member)
    portfolio_bytes=(directory/'portfolio.json').read_bytes()
    sarif_bytes=(directory/'results.sarif').read_bytes()
    seal_bytes=(directory/'SEAL.json').read_bytes()
    if sha(seal_bytes)!=latest.get('seal_sha256'):
        raise ValueError('AE-07 LATEST seal hash mismatch')
    if json.loads(seal_bytes)!={'schema':'ae07/artifact_seal/v1','generation':name,
                                  'artifacts':{'portfolio.json':sha(portfolio_bytes),
                                               'results.sarif':sha(sarif_bytes)}}:
        raise ValueError('AE-07 artifacts fail seal verification')
    record=json.loads(portfolio_bytes)
    sarif=json.loads(sarif_bytes)
    if (canonical(record)!=portfolio_bytes or canonical(sarif)!=sarif_bytes or
            name!='ae07-'+record.get('portfolio_sha256','')[:32]):
        raise ValueError('AE-07 noncanonical report or generation identity mismatch')
    if canonical(render_sarif(record))!=sarif_bytes:
        raise ValueError('AE-07 SARIF does not reproduce the source-bound findings')
    return record,sarif


def publish_portfolio(record: dict, output: Path | str, *, entries: list[dict]) -> dict:
    out=_path(output)
    _bounds(out,entries)
    with _locked(out):
        _atomic_bytes(out/'LATEST.json',canonical({'status':'running','generation':None}))
        try:
            verified=verify_portfolio(record,entries)
            generation='ae07-'+record['portfolio_sha256'][:32]
            portfolio_bytes=canonical(record)
            sarif_bytes=canonical(render_sarif(record))
            seal_bytes=canonical({'schema':'ae07/artifact_seal/v1','generation':generation,
                                  'artifacts':{'portfolio.json':sha(portfolio_bytes),
                                               'results.sarif':sha(sarif_bytes)}})
            generations=out/'generations'
            _no_symlink_components(generations)
            generations.mkdir(exist_ok=True)
            _no_symlink_components(generations)
            destination=generations/generation
            expected={'portfolio.json':portfolio_bytes,'results.sarif':sarif_bytes,'SEAL.json':seal_bytes}
            if destination.exists() or destination.is_symlink():
                _no_symlink_components(destination)
                if not destination.is_dir() or {p.name for p in destination.iterdir()}!=set(expected):
                    raise ValueError('Existing AE-07 generation is malformed')
                for name,blob in expected.items():
                    _no_symlink_components(destination/name)
                    if (destination/name).read_bytes()!=blob:
                        raise ValueError('Existing AE-07 historical generation was modified')
            else:
                stage=Path(tempfile.mkdtemp(dir=generations,prefix='.ae07-stage-'))
                try:
                    for name,blob in expected.items():
                        _atomic_bytes(stage/name,blob)
                    os.replace(stage,destination)
                    _fsync_dir(generations)
                finally:
                    if stage.exists(): shutil.rmtree(stage)
            _atomic_bytes(out/'LATEST.json',canonical({'status':'completed','generation':generation,
                                                       'seal_sha256':sha(seal_bytes)}))
            loaded,_=_stored(out)
            if canonical(loaded)!=portfolio_bytes:
                raise ValueError('AE-07 published report differs from verified input')
            return {'generation':generation,'seal_sha256':sha(seal_bytes),**verified}
        except BaseException as exc:
            _atomic_bytes(out/'LATEST.json',canonical({'status':'failed','generation':None,
                                                       'error_type':type(exc).__name__}))
            raise


def verify_portfolio_publication(output: Path | str, *, entries: list[dict]) -> dict:
    out=_path(output)
    _bounds(out,entries)
    record,sarif=_stored(out)
    verified=verify_portfolio(record,entries)
    if sarif!=render_sarif(record):
        raise ValueError('AE-07 SARIF differs from independently derived result')
    # Ensure the authoritative pointer did not change during input replay.
    final_record, _ = _stored(out)
    if canonical(final_record) != canonical(record):
        raise ValueError('AE-07 publication changed during independent verification')
    return {'generation':'ae07-'+record['portfolio_sha256'][:32],**verified,
            'sarif_results':len(sarif['runs'][0]['results'])}
