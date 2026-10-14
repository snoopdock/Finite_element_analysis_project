"""Generation-based artifact publication with a last-attempt marker.

Generation contents are written and fsynced before a single pointer promotion.
An interrupted attempt remains explicitly 'running', never a new clean result.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile


def canonical(data) -> bytes:
    return (json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _no_symlink_components(path: Path) -> None:
    path = Path(os.path.abspath(path))
    for current in (path, *path.parents):
        if current.is_symlink():
            raise ValueError(f'Symlink output path is forbidden: {current}')


def _atomic_bytes(path: Path, data: bytes) -> None:
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.ae01-write-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        _fsync_dir(path.parent)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def _existing(path: Path) -> dict:
    _no_symlink_components(path)
    return json.loads(path.read_text(encoding='utf-8'))


def verify(output: Path, *, source_root: Path | None = None, policy_file: Path | None = None) -> dict:
    """Independent byte-hash verification of the last *completed* generation."""
    _no_symlink_components(output)
    latest = _existing(Path(output) / 'LATEST.json')
    if latest['status'] != 'completed':
        raise ValueError(f'Latest attempt is not completed: {latest["status"]}')
    generation = latest['generation']
    if '/' in generation or generation.startswith('.'):
        raise ValueError('Invalid generation name')
    folder = Path(output) / 'generations' / generation
    _no_symlink_components(folder)
    _no_symlink_components(folder / 'SEAL.json')
    seal = (folder / 'SEAL.json').read_bytes()
    if sha(seal) != latest['seal_sha256']:
        raise ValueError('Generation seal mismatch')
    records = json.loads(seal)
    if set(p.name for p in folder.iterdir()) != set(records['artifacts']) | {'SEAL.json'}:
        raise ValueError('Generation artifact membership differs from seal')
    for name, expected in records['artifacts'].items():
        path = folder / name
        _no_symlink_components(path)
        if sha(path.read_bytes()) != expected:
            raise ValueError(f'Artifact checksum mismatch: {name}')
    report = json.loads((folder / 'report.json').read_bytes())
    _verify_contract(folder, report, source_root=source_root, policy_file=policy_file)
    if report['run_id'] != generation:
        raise ValueError('Run identifier mismatch')
    if report['execution_status'] != 'completed':
        raise ValueError('Published report is not completed')
    return {'generation': generation, 'verified_artifacts': sorted(records['artifacts']),
            'completeness': report['assurance_completeness'], 'findings': len(report['findings'])}


def _verify_contract(folder: Path, report: dict, *, source_root: Path | None, policy_file: Path | None) -> None:
    """Independent structural checks over the sealed report, graphs, manifest and G3 receipts."""
    from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph, SemanticNode, SemanticEdge
    from audit_engine.semantic_audit.graph.analysis.identity import graph_fingerprint, edge_fingerprint
    from .projection import project_imports
    from .source import inventory
    def read(name):
        return json.loads((folder / name).read_bytes())
    manifest = read('manifest.json')
    if sha(canonical(manifest)) != report['source_manifest_sha256']:
        raise ValueError('Source manifest digest mismatch')
    included = {row['path']: row['sha256'] for row in manifest['files'] if row['status'] == 'included'}
    if len(included) != manifest['summary']['included']:
        raise ValueError('Source manifest inclusion count mismatch')
    expected_source_digest = sha(canonical({'manifest_sha256': report['source_manifest_sha256'],
                                            'included': [[p, included[p]] for p in sorted(included)]}))
    if expected_source_digest != report['source_digest']:
        raise ValueError('Source byte digest aggregation mismatch')
    if source_root is not None:
        conf = read('policy.json')['configuration']
        live_manifest, _ = inventory(source_root, excludes=tuple(conf['excludes']), output=folder.parents[1])
        if live_manifest != manifest:
            raise ValueError('Source changed since audit publication')
    if policy_file is not None and sha(Path(policy_file).read_bytes()) != report['policy_sha256']:
        raise ValueError('Policy bytes changed since audit publication')
    graphs = []
    for name, key in (('graph.json', 'graph_fingerprint'), ('policy_graph.json', 'policy_graph_fingerprint')):
        data = read(name)
        graph = SemanticGraph(
            nodes=[SemanticNode(n['id'], n['type'], n['attributes'], n['metadata']) for n in data['nodes']],
            edges=[SemanticEdge(e['source'], e['target'], e['relation'], e['attributes'], e['metadata']) for e in data['edges']],
        )
        if graph_fingerprint(graph) != report[key]:
            raise ValueError(f'Graph fingerprint disagreement: {name}')
        graphs.append(graph)
    _, policy_graph = graphs
    module_sources = sorted({e.source_id for e in policy_graph.edges if e.relation_type == 'IMPORTS'})
    executions = read('rule_executions.json')
    if [row['source_module'] for row in executions] != [name.removeprefix('module:') for name in module_sources]:
        raise ValueError('Rule execution does not cover all dependency sources')
    all_receipts = {}
    selected_edges = 0
    for row in executions:
        scope = project_imports(policy_graph, 'module:' + row['source_module'])
        actual_fingerprint = graph_fingerprint(scope)
        if row['source_projection_fingerprint'] != actual_fingerprint:
            raise ValueError('Source projection fingerprint mismatch')
        execution = row['rule_execution']
        if execution['reason'] != 'executed':
            raise ValueError('Required architecture rule was not executed')
        if len(execution['obligations']) != len(scope.edges) or len(execution['receipts']) != len(scope.edges):
            raise ValueError('Rule coverage does not match applicable import occurrences')
        selected_edges += len(scope.edges)
        edge_ids = {edge_fingerprint(e) for e in scope.edges}
        for receipt in execution['receipts']:
            if receipt['graph_fingerprint'] != actual_fingerprint:
                raise ValueError('Receipt graph binding mismatch')
            if len(receipt['evidence_ids']) != 1 or receipt['evidence_ids'][0] not in edge_ids:
                raise ValueError('Receipt occurrence evidence is absent from the projected source graph')
            if receipt['receipt_id'] in all_receipts:
                raise ValueError('Duplicate receipt identity')
            all_receipts[receipt['receipt_id']] = receipt
    if selected_edges != report['applicable_observations']:
        raise ValueError('Report applicability count disagrees with graph evidence')
    findings = report['findings']
    if report['counts']['verified_findings'] != len(findings):
        raise ValueError('Finding count mismatch')
    for entry in findings:
        finding, witness = entry['finding'], entry['witness']
        receipt = all_receipts.get(finding['receipt_id'])
        if receipt is None or receipt['decision'] != 'confirmed' or receipt['evidence_state'] != 'validated':
            raise ValueError('Finding lacks a confirming validated receipt')
        if receipt['evidence_ids'] != finding['evidence_ids']:
            raise ValueError('Finding witness differs from receipt')
        if included.get(witness['source_id']) != witness['source_sha256']:
            raise ValueError('Finding source hash does not match included source')
        if not any(edge_fingerprint(e) in finding['evidence_ids'] and e.metadata == witness
                   for e in policy_graph.edges):
            raise ValueError('Finding source witness cannot be independently reproduced')
    expected_compliance = report['assurance_completeness'] == 'complete_within_declared_scope' and not findings and selected_edges > 0
    if report['verified_compliance'] != expected_compliance:
        raise ValueError('False-clean or inconsistent assurance verdict')
    if (report['assurance_completeness'] == 'complete_within_declared_scope') == bool(report['issues']):
        raise ValueError('Report assurance completeness disagrees with declared issues')


@contextlib.contextmanager
def attempt(output: Path):
    """Serialize publication; last-attempt record invalidates stale successful claims."""
    import fcntl
    output = Path(os.path.abspath(output))
    _no_symlink_components(output)
    output.mkdir(parents=True, exist_ok=True)
    _no_symlink_components(output)
    lock_fd = os.open(output / '.ae01.lock', os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        _atomic_bytes(output / 'LATEST.json', canonical({'status': 'running', 'generation': None}))
        try:
            yield output
        except BaseException as exc:
            _atomic_bytes(output / 'LATEST.json', canonical({'status': 'failed', 'generation': None,
                                                            'error_type': type(exc).__name__, 'reason': str(exc)[:300]}))
            raise
    finally:
        os.close(lock_fd)


def publish(output: Path, run_id: str, artifacts: dict[str, object]) -> dict:
    if not run_id.startswith('ae01-') or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in run_id):
        raise ValueError('Unsafe run identifier')
    generations = output / 'generations'
    generations.mkdir(exist_ok=True)
    _no_symlink_components(generations)
    stage = Path(tempfile.mkdtemp(prefix='.staging-', dir=generations))
    try:
        hashes = {}
        for name, payload in sorted(artifacts.items()):
            if '/' in name or name.startswith('.') or name == 'SEAL.json':
                raise ValueError('Invalid artifact name')
            data = canonical(payload)
            _atomic_bytes(stage / name, data)
            hashes[name] = sha(data)
        seal = canonical({'schema': 'ae01/artifact_seal/v1', 'artifacts': hashes})
        _atomic_bytes(stage / 'SEAL.json', seal)
        target = generations / run_id
        if target.exists() or target.is_symlink():
            _no_symlink_components(target)
            if not target.is_dir() or set(p.name for p in target.iterdir()) != set(hashes) | {'SEAL.json'}:
                raise ValueError('Previously published generation disagrees with new run')
            for name, expected in hashes.items():
                _no_symlink_components(target / name)
                if sha((target / name).read_bytes()) != expected:
                    raise ValueError('Previously published generation was modified')
            _no_symlink_components(target / 'SEAL.json')
            if (target / 'SEAL.json').read_bytes() != seal:
                raise ValueError('Previously published seal was modified')
        else:
            os.rename(stage, target)
            _fsync_dir(generations)
        latest = {'status': 'completed', 'generation': run_id, 'seal_sha256': sha(seal)}
        _atomic_bytes(output / 'LATEST.json', canonical(latest))
        return verify(output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
