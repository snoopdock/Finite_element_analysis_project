"""AE-03 bounded, isolated *workspace* mutation experiment.

Subprocesses are not an operating-system security sandbox. Only execute
trusted repository tests in an already-isolated CI/container environment.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Iterable

from audit_engine.semantic_audit.ae01.publication import canonical, sha, _no_symlink_components
from .source import EXCLUDED_DIRS, Mutation, checked_relative, discover, safe_file, verify_mutation


@dataclass(frozen=True)
class TestResult:
    status: str
    return_code: int | None
    output_sha256: str
    output_preview: str

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _check_tree(root: Path, *, max_files: int = 15000, max_bytes: int = 300_000_000) -> None:
    root = root.absolute()
    _no_symlink_components(root)
    count, total = 0, 0
    for current, directories, files in os.walk(root, followlinks=False):
        directories[:] = sorted(d for d in directories if d not in EXCLUDED_DIRS)
        for d in directories:
            if (Path(current) / d).is_symlink():
                raise ValueError('Source directory symlink forbidden')
        for name in files:
            candidate = Path(current) / name
            if candidate.is_symlink():
                raise ValueError(f'Source file symlink forbidden: {candidate.relative_to(root)}')
            count += 1
            total += candidate.stat().st_size
            if count > max_files or total > max_bytes:
                raise ValueError('Workspace exceeds explicit copy budget')


def _workspace_manifest(root: Path) -> dict:
    '''Hash the exact local workspace copied for trials (not just selected files).'''
    _check_tree(root)
    members = []
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS)
        for name in sorted(files):
            file = Path(current) / name
            members.append([file.relative_to(root).as_posix(), sha(file.read_bytes())])
    return {'files': len(members), 'digest': sha(canonical(members)),
            'exclusions': sorted(EXCLUDED_DIRS)}


def _copy(root: Path, destination: Path) -> None:
    _check_tree(root)
    shutil.copytree(root, destination, ignore=shutil.ignore_patterns(*EXCLUDED_DIRS), symlinks=False)


def _selected_tests(root: Path, tests: Iterable[str]) -> tuple[str, ...]:
    checked = tuple(sorted(set(checked_relative(str(t)) for t in tests)))
    if not checked or any(not t.startswith('tests/') for t in checked):
        raise ValueError('Explicit test files under tests/ are required')
    for rel in checked:
        safe_file(root, rel)
    return checked


def _execute(workspace: Path, tests: tuple[str, ...], timeout: int) -> TestResult:
    env = dict(os.environ)
    env.update({'PYTHONPATH': str(workspace), 'PYTHONDONTWRITEBYTECODE': '1',
                'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'PYTEST_ADDOPTS': '',
                'PYTHONHASHSEED': '0'})
    cmd = [sys.executable, '-m', 'pytest', '-q', '--maxfail=1', *tests]
    try:
        result = subprocess.run(cmd, cwd=workspace, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=timeout, check=False)
        output = result.stdout
        status = 'passed' if result.returncode == 0 else 'failed'
        code = result.returncode
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or b''
        status, code = 'timeout', None
    return TestResult(status, code, sha(output), output.decode('utf-8', errors='replace')[-1000:])


def _trial(root: Path, tests: tuple[str, ...], timeout: int, mutation: Mutation | None = None,
           mutated_bytes: bytes | None = None) -> TestResult:
    with tempfile.TemporaryDirectory(prefix='ae03-trial-') as temporary:
        workspace = Path(temporary) / 'work'
        _copy(root, workspace)
        if mutation is not None:
            if mutated_bytes is None:
                raise ValueError('Missing altered source bytes')
            dest = workspace / mutation.path
            if sha(dest.read_bytes()) != mutation.source_sha256:
                raise ValueError('Workspace source-byte mismatch before mutation')
            dest.write_bytes(mutated_bytes)
            if sha(dest.read_bytes()) != mutation.mutated_sha256:
                raise ValueError('Mutation not applied as requested')
        return _execute(workspace, tests, timeout)


def run_experiment(root: Path, sources: Iterable[str], tests: Iterable[str], *,
                   max_mutants: int = 20, timeout: int = 30,
                   impact: object | None = None) -> dict:
    """Run one independently scoped mutation experiment against trusted tests.

    A baseline failure causes *no mutant execution*. Invalid mutants (syntax
    failure), timeouts and other execution faults are excluded from the scored
    denominator. The score is descriptive, not a confidence interval.
    """
    root = Path(root).absolute()
    if not root.is_dir():
        raise ValueError('Missing repository root')
    if not isinstance(max_mutants, int) or not 1 <= max_mutants <= 100:
        raise ValueError('max_mutants must be within [1,100]')
    if not isinstance(timeout, int) or not 1 <= timeout <= 300:
        raise ValueError('timeout must be within [1,300] seconds')
    files = tuple(sorted(set(str(f) for f in sources)))
    targets = _selected_tests(root, tests)
    sites = discover(root, files)
    if not sites:
        raise ValueError('No supported mutation sites in declared source scope')
    workspace_manifest = _workspace_manifest(root)
    source_hashes = {path: sha(safe_file(root, path).read_bytes()) for path in files}
    test_hashes = {path: sha(safe_file(root, path).read_bytes()) for path in targets}
    provenance = None
    if impact is not None:
        # Inputs to this interface MUST be rederived from AE-02 verified
        # generations using verified_impact(). An arbitrary JSON plan must
        # not be accepted by the runtime.
        from .impact import VerifiedImpact
        if not isinstance(impact, VerifiedImpact):
            raise TypeError('Impact context must be independently verified')
        referenced = {f for task in impact.record['impact_plan']['tasks'] for f in task['source_files']}
        if not set(files).issubset(referenced):
            raise ValueError('Requested source is outside verified impact task scope')
        provenance = impact.to_dict()
    baseline = _trial(root, targets, timeout)
    rows = []
    for mutation, altered in sites[:max_mutants] if baseline.status == 'passed' else ():
        # pre-flight independent mutation witness and byte-level compiler
        altered = verify_mutation(root, mutation)
        try:
            ast.parse(altered.decode('utf-8'), filename=mutation.path)
        except SyntaxError:
            rows.append({'mutation': mutation.to_dict(), 'outcome': 'invalid_mutant', 'test': None})
            continue
        outcome = _trial(root, targets, timeout, mutation, altered)
        state = ('killed' if outcome.return_code == 1 else
                 'survived' if outcome.status == 'passed' else
                 'timeout' if outcome.status == 'timeout' else 'runner_error')
        rows.append({'mutation': mutation.to_dict(), 'outcome': state, 'test': outcome.to_dict()})
    # The selected source and test content must still match the original read
    # (we never write into the supplied root).
    if _workspace_manifest(root) != workspace_manifest:
        raise ValueError('Workspace bytes changed during mutation evaluation')
    for path, digest in {**source_hashes, **test_hashes}.items():
        if sha(safe_file(root, path).read_bytes()) != digest:
            raise ValueError('Source changed during mutation evaluation')
    killed = sum(r['outcome'] == 'killed' for r in rows)
    survived = sum(r['outcome'] == 'survived' for r in rows)
    invalid = sum(r['outcome'] == 'invalid_mutant' for r in rows)
    timed_out = sum(r['outcome'] == 'timeout' for r in rows)
    runner_errors = sum(r['outcome'] == 'runner_error' for r in rows)
    scored = killed + survived
    incomplete = (baseline.status != 'passed' or invalid > 0 or timed_out > 0 or runner_errors > 0 or
                  len(sites) > max_mutants or
                  (provenance is not None and (provenance['truncated'] or
                   provenance['completeness'] == 'full_review_required')))
    record = {
        'schema': 'ae03/mutation_audit/v1',
        'source_hashes': source_hashes, 'test_hashes': test_hashes,
        'workspace_manifest': workspace_manifest,
        'python_version': '.'.join(map(str, sys.version_info[:3])),
        'pytest_isolated': True, 'timeout_seconds': timeout,
        'max_mutants': max_mutants, 'available_sites': len(sites),
        'impact_provenance': provenance,
        'baseline': baseline.to_dict(), 'mutants': rows,
        'counts': {'killed': killed, 'survived': survived,
                   'invalid_mutant': invalid, 'timeout': timed_out, 'runner_error': runner_errors,
                   'executed_valid': scored, 'not_executed': len(sites) - len(rows)},
        'mutation_score': (killed / scored) if scored else None,
        'assurance': ('inconclusive_baseline' if baseline.status != 'passed' else
                      'partial_experiment' if incomplete else 'complete_for_selected_sites'),
        'interpretation': ('Mutant outcomes concern only tested operators, exact source and selected tests; '
                           'surviving mutant is not a production defect; killed mutant is not proof '
                           'of comprehensive test quality or scientific correctness.'),
    }
    record['record_sha256'] = sha(canonical(record))
    return record


def verify_record(record: dict, root: Path, *, replay: bool = False,
                  verified_impact_context: object | None = None) -> dict:
    """Verify witness bytes and report accounting; replay executes trusted tests.

    Without replay, this verifies report consistency and source binding, NOT
    claimed subprocess outcomes. For detached outcome evidence use replay=True.
    """
    if not isinstance(record, dict) or record.get('schema') != 'ae03/mutation_audit/v1':
        raise ValueError('Invalid AE-03 report schema')
    content = {k: v for k, v in record.items() if k != 'record_sha256'}
    if sha(canonical(content)) != record.get('record_sha256'):
        raise ValueError('Mutation audit report hash mismatch')
    root = Path(root).absolute()
    if _workspace_manifest(root) != record['workspace_manifest']:
        raise ValueError('Live workspace bytes disagree with audit manifest')
    for path, digest in {**record['source_hashes'], **record['test_hashes']}.items():
        if sha(safe_file(root, path).read_bytes()) != digest:
            raise ValueError('Live file bytes disagree with AE-03 source/test witness')
    # Account for identity, operator witnesses, score and selected scope.
    sources = tuple(sorted(record['source_hashes']))
    sites = discover(root, sources)
    if len(sites) != record['available_sites']:
        raise ValueError('Mutation site inventory changed')
    expected = [item.to_dict() for item, _ in sites[:record['max_mutants']]]
    actual = [row['mutation'] for row in record['mutants']]
    if actual != expected[:len(actual)]:
        raise ValueError('Mutation occurrence list disagrees with source')
    if record['baseline']['status'] != 'passed' and actual:
        raise ValueError('Mutations cannot execute on failing baseline')
    outcomes = [row['outcome'] for row in record['mutants']]
    for status, key in [('killed', 'killed'), ('survived', 'survived'),
                        ('invalid_mutant', 'invalid_mutant'), ('timeout', 'timeout'), ('runner_error', 'runner_error')]:
        if outcomes.count(status) != record['counts'][key]:
            raise ValueError('Reported mutation count mismatch')
    scored = outcomes.count('killed') + outcomes.count('survived')
    if (record['counts']['executed_valid'] != scored or
            record['counts']['not_executed'] != len(sites) - len(actual) or
            record['mutation_score'] != (outcomes.count('killed') / scored if scored else None)):
        raise ValueError('Mutation denominator mismatch')
    expected_assurance = ('inconclusive_baseline' if record['baseline']['status'] != 'passed' else
                          'partial_experiment' if any(x in outcomes for x in
                              ('invalid_mutant', 'timeout', 'runner_error')) or len(actual) < len(sites) or
                          (record['impact_provenance'] is not None and
                           (record['impact_provenance']['truncated'] or
                            record['impact_provenance']['completeness'] == 'full_review_required')) else
                          'complete_for_selected_sites')
    if record['assurance'] != expected_assurance:
        raise ValueError('Assurance state inconsistent with evidence coverage')
    if verified_impact_context is not None:
        from .impact import VerifiedImpact
        if (not isinstance(verified_impact_context, VerifiedImpact) or
                verified_impact_context.to_dict() != record['impact_provenance']):
            raise ValueError('Sealed AE-02 impact provenance mismatch')
    if replay:
        # Stable statuses are the contract; captured stdout contains run-specific
        # timings/paths, and its hash is intentionally not used as a replay oracle.
        again = run_experiment(root, sources, record['test_hashes'],
                               max_mutants=record['max_mutants'], timeout=record['timeout_seconds'])
        if (again['baseline']['status'] != record['baseline']['status'] or
                [row['outcome'] for row in again['mutants']] != outcomes or
                again['source_hashes'] != record['source_hashes']):
            raise ValueError('Test outcomes differ on independent replay (possible flaky test)')
    return {'source_binding': 'verified', 'accounting': 'verified',
            'test_outcomes': 'replayed' if replay else 'not_verified_without_replay',
            'impact_provenance': ('not_applicable' if record['impact_provenance'] is None else
                                  'verified' if verified_impact_context is not None else
                                  'not_verified_without_sealed_generations')}
