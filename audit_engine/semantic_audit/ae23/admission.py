"""Bounded, offline, Git-tree-bound source admission for externally sourced cases.

A Git object match proves internal consistency against the supplied commit, not
that the commit came from the claimed upstream owner. An editable provenance
manifest or two self-reported reviewers cannot create external authentication.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path, PurePosixPath
from typing import Mapping

from audit_engine.semantic_audit.ae01.publication import canonical, _no_symlink_components

LOCK_SCHEMA = 'ae23/external_case_lock/v1'
MAX_CASES = 32
MAX_FILE_BYTES = 120_000
MAX_LOCK_BYTES = 120_000
HEX_OID = re.compile(r'(?:[a-f0-9]{40}|[a-f0-9]{64})\Z')
HEX_SHA256 = re.compile(r'[a-f0-9]{64}\Z')
IDENT = re.compile(r'[A-Za-z][A-Za-z0-9_-]{0,79}\Z')


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_canonical(path: Path | str, *, limit: int = MAX_LOCK_BYTES) -> tuple[dict, str]:
    p = Path(os.path.abspath(path))
    _no_symlink_components(p)
    if not p.is_file() or not stat.S_ISREG(p.lstat().st_mode) or p.stat().st_size > limit:
        raise ValueError('Reference must be a bounded regular file')
    raw = p.read_bytes()
    obj = json.loads(raw)
    if not isinstance(obj, dict) or canonical(obj) != raw:
        raise ValueError('Reference must be canonical JSON object')
    return obj, sha(raw)


def _identifier(value: object, name: str) -> str:
    if not isinstance(value, str) or not IDENT.fullmatch(value):
        raise ValueError('Invalid ' + name)
    return value


def _source_path(value: object) -> str:
    if not isinstance(value, str) or not value.endswith('.py') or '\\' in value or '\x00' in value:
        raise ValueError('Invalid repository source path')
    p = PurePosixPath(value)
    if (p.is_absolute() or not p.parts or any(t in {'.', '..', ''} for t in value.split('/'))
            or str(p) != value):
        raise ValueError('Unsafe repository source path')
    return value


def validate_lock(lock: dict) -> None:
    if set(lock) != {'schema', 'dataset', 'repositories', 'cases', 'protocol'} or lock['schema'] != LOCK_SCHEMA:
        raise ValueError('Unsupported reference lock contract')
    _identifier(lock['dataset'], 'dataset ID')
    if lock['protocol'] != {'execution': 'static_only', 'source_authority': 'git_tree_integrity_only',
                            'review_policy': 'two_distinct_reviewers_required_for_adjudicated_subset'}:
        raise ValueError('Protocol cannot claim unsupported execution or provenance authority')
    repos = lock['repositories']
    if not isinstance(repos, dict) or not repos:
        raise ValueError('No repositories declared')
    for k, v in repos.items():
        _identifier(k, 'repository key')
        if not isinstance(v, dict) or set(v) != {'claimed_upstream_url'}:
            raise ValueError('Invalid repository declaration')
        if not isinstance(v['claimed_upstream_url'], str) or not v['claimed_upstream_url'].startswith('https://'):
            raise ValueError('Upstream URL must be a declarative HTTPS URL')
    cases = lock['cases']
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise ValueError('Invalid case count')
    seen, blobs_by_split = set(), {'development': set(), 'holdout': set()}
    for c in cases:
        if not isinstance(c, dict) or set(c) != {'case_id', 'repository', 'family', 'split', 'scope',
                                                 'signal_variable', 'faulty', 'correct'}:
            raise ValueError('Malformed case record')
        cid = _identifier(c['case_id'], 'case ID')
        if cid in seen:
            raise ValueError('Duplicate case identity')
        seen.add(cid)
        if c['repository'] not in repos:
            raise ValueError('Unknown declared source repository')
        _identifier(c['family'], 'defect family')
        if c['split'] not in blobs_by_split or c['scope'] not in {'bounded_static', 'unsupported_semantics'}:
            raise ValueError('Invalid split or static scope')
        if c['signal_variable'] is not None and (not isinstance(c['signal_variable'], str)
              or not c['signal_variable'].isidentifier()):
            raise ValueError('Invalid signal variable')
        if c['scope'] == 'bounded_static' and not c['signal_variable']:
            raise ValueError('In-scope analysis requires an explicitly declared variable')
        refs = []
        for role in ('faulty', 'correct'):
            ref = c[role]
            if not isinstance(ref, dict) or set(ref) != {'commit', 'path', 'git_blob_oid', 'sha256'}:
                raise ValueError('Invalid Git source reference')
            if (not isinstance(ref['commit'], str) or not HEX_OID.fullmatch(ref['commit'])
                or not isinstance(ref['git_blob_oid'], str) or not HEX_OID.fullmatch(ref['git_blob_oid'])
                or not isinstance(ref['sha256'], str) or not HEX_SHA256.fullmatch(ref['sha256'])):
                raise ValueError('Git and SHA-256 identities must be full hashes')
            _source_path(ref['path'])
            refs.append((ref['commit'], ref['path'], ref['sha256']))
            blobs_by_split[c['split']].add(ref['sha256'])
        if refs[0] == refs[1] or refs[0][2] == refs[1][2]:
            raise ValueError('A faulty/correct pair must have distinct bytes')
    if blobs_by_split['development'] & blobs_by_split['holdout']:
        raise ValueError('Holdout/development source-byte leakage')


def _git(repo: Path, args: list[str], *, max_bytes: int = 200_000) -> bytes:
    env = dict(os.environ)
    env.update({'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
                'GIT_OPTIONAL_LOCKS': '0', 'GIT_NO_REPLACE_OBJECTS': '1',
                'GIT_PROTOCOL_FROM_USER': '0', 'GIT_TERMINAL_PROMPT': '0'})
    completed = subprocess.run(['git', '--no-pager', '--literal-pathspecs', '-C', str(repo), *args],
                               env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=12, check=False)
    if completed.returncode:
        raise ValueError('Git source-reference verification failed')
    if len(completed.stdout) > max_bytes:
        raise ValueError('Git object response exceeds bounded size')
    return completed.stdout


def git_source(repo: Path | str, ref: dict) -> tuple[bytes, dict]:
    """Verify commit -> tree -> regular Git blob -> exact SHA-256, without checkout."""
    repo = Path(os.path.abspath(repo))
    _no_symlink_components(repo)
    if not repo.is_dir():
        raise ValueError('Repository is not a real directory')
    commit, path = ref['commit'], _source_path(ref['path'])
    if _git(repo, ['cat-file', '-t', commit], max_bytes=100).strip() != b'commit':
        raise ValueError('Reference object is not a commit')
    # --full-tree and literal pathspec; reject ambiguous/multiple entries.
    tree = _git(repo, ['ls-tree', '-z', '--full-tree', commit, '--', path], max_bytes=4000)
    entries = [x for x in tree.split(b'\0') if x]
    if len(entries) != 1:
        raise ValueError('Source not uniquely present in referenced commit tree')
    try:
        left, raw_path = entries[0].split(b'\t', 1)
        mode, typ, oid = left.decode('ascii').split(' ')
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError('Invalid Git tree entry') from exc
    if mode not in {'100644', '100755'} or typ != 'blob' or raw_path != path.encode('utf-8'):
        raise ValueError('Git tree reference is not the requested regular source file')
    if oid != ref['git_blob_oid']:
        raise ValueError('Declared blob not attached to commit and source path')
    size_raw = _git(repo, ['cat-file', '-s', oid], max_bytes=100).strip()
    if not size_raw.isdigit() or int(size_raw) > MAX_FILE_BYTES:
        raise ValueError('Git source object exceeds size limit')
    source = _git(repo, ['cat-file', 'blob', oid], max_bytes=MAX_FILE_BYTES)
    if len(source) != int(size_raw) or sha(source) != ref['sha256']:
        raise ValueError('Git source bytes differ from independently declared SHA-256')
    # Recompute the Git blob object's digest instead of trusting git cat-file metadata alone.
    import hashlib as _hash
    expected_git_hash = _hash.sha256 if len(oid) == 64 else _hash.sha1
    reconstructed = expected_git_hash(b'blob ' + str(len(source)).encode() + b'\0' + source).hexdigest()
    if reconstructed != oid:
        raise ValueError('Git blob content identity mismatch')
    return source, {'commit': commit, 'path': path, 'git_blob_oid': oid,
                    'sha256': ref['sha256'], 'git_tree_binding': 'verified',
                    'upstream_owner_authenticated': False}


def admit(lock_path: Path | str, repositories: Mapping[str, Path | str]) -> dict:
    lock, lock_digest = read_canonical(lock_path)
    validate_lock(lock)
    if set(repositories) != set(lock['repositories']):
        raise ValueError('Repository root mappings do not exactly match lock')
    sources, cases = {}, []
    for c in lock['cases']:
        matched = {}
        for role in ('faulty', 'correct'):
            data, prov = git_source(repositories[c['repository']], c[role])
            key = f"{c['case_id']}_{role}.py"
            sources[key] = data
            matched[role] = prov
        cases.append({'case_id': c['case_id'], 'family': c['family'], 'split': c['split'],
                      'scope': c['scope'], 'signal_variable': c['signal_variable'],
                      'repository': c['repository'], 'source_bindings': matched})
    return {'lock': lock, 'lock_sha256': lock_digest, 'cases': cases, 'sources': sources,
            'authority': 'locally_supplied_git_objects_integrity_checked__upstream_origin_not_authenticated'}
