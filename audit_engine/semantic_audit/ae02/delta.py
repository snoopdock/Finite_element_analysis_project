"""Source, dependency and evidence delta over independently verified generations.

The old generic boolean-only delta is retained as a summary *inside* a richer
source-bound comparison. No graph change is intrinsically called a defect.
"""
from __future__ import annotations
from dataclasses import dataclass
from audit_engine.semantic_audit.ae01.publication import canonical, sha


@dataclass(frozen=True)
class AuditDelta:
    previous_generation: str
    current_generation: str
    source_changed: bool
    graph_changed: bool
    findings_changed: bool
    policy_changed: bool
    added_files: tuple[str, ...]
    removed_files: tuple[str, ...]
    modified_files: tuple[str, ...]
    added_dependencies: tuple[dict, ...]
    removed_dependencies: tuple[dict, ...]
    changed_import_observations: tuple[str, ...]

    def to_dict(self) -> dict:
        return {k: list(v) if isinstance(v, tuple) else v for k, v in self.__dict__.items()}


def _included(g) -> dict[str, str]:
    return {r['path']: r['sha256'] for r in g.manifest['files'] if r['status'] == 'included'}


def _dependencies(g) -> dict[str, dict]:
    # Import identity is a source occurrence, not a dependency string.
    return {i['id']: {'id': i['id'], 'file': i['file'], 'line': i['line'], 'column': i['column'],
                      'module': i['module'], 'target': i['target'],
                      'context': i['context'], 'alias': i['alias'], 'status': i['status']}
            for i in g.facts['imports'] if i['status'] == 'internal'}


def compare_snapshots(before, after) -> AuditDelta:
    """Compare verified generation objects; rejects bare unauthenticated dicts."""
    from .snapshots import VerifiedGeneration
    if not isinstance(before, VerifiedGeneration) or not isinstance(after, VerifiedGeneration):
        raise TypeError('AE-02 comparisons require sealed, verified AE-01 generations')
    a, b = _included(before), _included(after)
    ia, ib = _dependencies(before), _dependencies(after)
    changed = tuple(sorted(k for k in ia.keys() & ib.keys() if ia[k] != ib[k]))
    removed = sorted((ia.keys() - ib.keys()) | set(changed))
    added = sorted((ib.keys() - ia.keys()) | set(changed))
    return AuditDelta(
        before.snapshot.generation_id, after.snapshot.generation_id,
        before.snapshot.source_digest != after.snapshot.source_digest,
        before.snapshot.graph_hash != after.snapshot.graph_hash,
        before.snapshot.finding_hash != after.snapshot.finding_hash,
        (before.snapshot.policy_hash != after.snapshot.policy_hash or
         before.policy['configuration']['lifecycle'] != after.policy['configuration']['lifecycle']),
        tuple(sorted(b.keys() - a.keys())), tuple(sorted(a.keys() - b.keys())),
        tuple(sorted(k for k in a.keys() & b.keys() if a[k] != b[k])),
        tuple(ib[k] for k in added),
        tuple(ia[k] for k in removed), changed,
    )
