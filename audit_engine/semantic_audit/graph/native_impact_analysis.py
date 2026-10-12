"""GE-03: verified, read-only scientific graph change-impact reports.

Native integration with GE-01 views, GE-02 persistent CAS graph-state, and
SemanticGraphEvolutionService. A review candidate is NOT a proven derivation,
scientific correctness determination, or authorization to mutate a graph.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

from audit_engine.semantic_audit.graph.domain_integration import (
    GraphDomainError, _read_json, from_scientific_graph,
)
from audit_engine.semantic_audit.graph.persistent_domain_state import (
    GraphStoreError, PersistentDomainGraphStore, _input_path, _transition,
    canonical, sha,
)

SCHEMA = 'ge03-verified-impact-report/v1'
MAX_REPORT_BYTES = 16_000_000

class GE03Error(ValueError):
    """Unsafe source, invalid transition, or inconsistent impact."""


def _safe_store(repo: Path, name: str) -> Path:
    relative = Path(name)
    if (relative.is_absolute() or '..' in relative.parts or
            relative.parts[:1] != ('.graph-state',) or len(relative.parts) < 2):
        raise GE03Error('Store must be beneath repository .graph-state/')
    path = repo / relative
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise GE03Error('Symlinked store path is prohibited')
    return path


def _change_ids(delta: dict) -> dict[str, list[str]]:
    """Extract bounded structural change IDs from native GraphDelta.to_dict()."""
    if not isinstance(delta, dict) or delta.get('schema_version') != 'semantic_graph_delta/v1':
        raise GE03Error('Invalid native graph delta')
    result = {}
    for key in ('added_nodes', 'removed_nodes', 'modified_nodes'):
        values = delta.get(key)
        if not isinstance(values, list):
            raise GE03Error('Invalid native delta '+key)
        ids = [entry['node_id'] if key == 'modified_nodes' else entry['id'] for entry in values]
        if len(ids) != len(set(ids)) or not all(isinstance(i,str) and i for i in ids):
            raise GE03Error('Invalid/duplicate node IDs')
        result[key] = sorted(ids)
    for key in ('added_edges', 'removed_edges'):
        values = delta.get(key)
        if not isinstance(values, list):
            raise GE03Error('Invalid native delta '+key)
        result[key] = sorted(f"{e['source']} --{e['relation']}--> {e['target']}" for e in values)
    return result


def analyze(repo: str | Path, *, mode: str = 'candidate',
            knowledge_graph: str | None = None,
            store: str = '.graph-state/scientific') -> dict[str, Any]:
    """Verify GE-02 history then derive the native structural review frontier."""
    repo = Path(repo).resolve(strict=True)
    if not repo.is_dir():
        raise GE03Error('Repository is not a directory')
    root = _safe_store(repo, store)
    state_store = PersistentDomainGraphStore(root)
    state = state_store.verify()   # verifies *all* reachable CAS commits and transitions
    if state['status'] != 'verified' or state.get('domain') != 'scientific_knowledge':
        raise GE03Error('Verified scientific GE-02 baseline required; run GE-02 first')
    current = state_store.current_view()
    if current is None:
        raise GE03Error('Missing verified current view')
    transition = None
    candidate_snapshot_sha = None
    candidate_input_sha = None
    baseline_snapshot_sha = state['snapshot_sha256']
    status = 'review_candidates_only'
    if mode == 'candidate':
        if not knowledge_graph:
            raise GE03Error('Candidate mode requires --knowledge-graph')
        try:
            source = _input_path(repo, knowledge_graph)
            view = from_scientific_graph(_read_json(source))
        except (GraphDomainError, GraphStoreError, OSError, ValueError) as exc:
            raise GE03Error('Invalid or unsafe candidate scientific graph') from exc
        if view.domain != current.domain:
            raise GE03Error('Cross-domain comparison prohibited')
        transition = _transition(current, view)  # established evolution + GE-02 frontier
        candidate_snapshot_sha = view.snapshot()['snapshot_sha256']
        candidate_input_sha = view.input_sha256
    elif mode == 'latest-transition':
        if knowledge_graph:
            raise GE03Error('--knowledge-graph is not valid in latest-transition mode')
        receipt = state_store._cas_read('commits', state['head'])
        if state['generation'] == 1:
            status = 'no_prior_transition'
        else:
            digest = receipt['transition_object_sha256']
            if not isinstance(digest, str):
                raise GE03Error('Verified history missing transition object')
            transition = state_store._cas_read('transitions', digest)
            # store.verify() independently reconstructs and checks this transition
            candidate_snapshot_sha = state['snapshot_sha256']
            candidate_input_sha = receipt['input_sha256']
            parent = state_store._cas_read('commits', receipt['parent_receipt_sha256'])
            prior = state_store._cas_read('objects', parent['snapshot_object_sha256'])
            baseline_snapshot_sha = prior['snapshot_sha256']
    else:
        raise GE03Error('Unsupported mode')

    if transition is not None:
        if transition.get('schema_version') != 'ge02-graph-transition/v1':
            raise GE03Error('Unexpected native transition contract')
        impact, delta = transition['impact'], transition['graph_delta']
        if (impact.get('status') != 'review_candidates_only' or
            impact.get('scientific_truth_established') is not False or
            impact.get('automatic_approval_permitted') is not False):
            raise GE03Error('Unsafe impact authorization assertion')
        changed = _change_ids(delta)
        candidates = impact['review_candidates']
        if not isinstance(candidates, list) or len(candidates) > 50000:
            raise GE03Error('Invalid impact frontier')
        if delta['is_noop'] and candidates:
            raise GE03Error('No-op cannot yield structural review candidates')
        if delta['is_noop']:
            status = 'no_structural_change'
    else:
        delta = None
        changed = {name: [] for name in ('added_nodes','removed_nodes','modified_nodes','added_edges','removed_edges')}
        candidates = []

    report = {
        'schema_version': SCHEMA,
        'mode': mode,
        'status': status,
        'store_head_sha256': state['head'],
        'store_generation': state['generation'],
        'domain': state['domain'],
        'before_graph_fingerprint': (transition['before_graph_fingerprint'] if transition else current.fingerprint),
        'after_graph_fingerprint': (transition['after_graph_fingerprint'] if transition else current.fingerprint),
        'baseline_snapshot_sha256': baseline_snapshot_sha,
        'compared_snapshot_sha256': candidate_snapshot_sha,
        'compared_input_sha256': candidate_input_sha,
        'delta_id': delta['delta_id'] if delta else None,
        'delta_is_noop': delta['is_noop'] if delta else None,
        'direct_changes': changed,
        'review_candidates': candidates,
        'review_candidate_count': len(candidates),
        'unmapped_document_section_ids': [],
        'document_section_mapping_available': False,
        'scientific_truth_established': False,
        'automatic_approval_permitted': False,
        'authoritative_graph_mutation_permitted': False,
        'provenance_verified': True,
        'review_scope': 'structural_dependency_only',
    }
    encoded = canonical(report)
    if len(encoded) > MAX_REPORT_BYTES:
        raise GE03Error('Impact report exceeds resource budget')
    report['report_sha256'] = sha(encoded)
    return report


def _write_report(destination: Path, report: dict):
    destination = Path(os.path.abspath(destination))
    if any(part.is_symlink() for part in (destination, *destination.parents)):
        raise GE03Error('Symlinked output directory is forbidden')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # create-exclusively: no replacement of a previous report, even if corrupted
    try:
        fd = os.open(destination, os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0), 0o600)
    except OSError as exc:
        raise GE03Error('Unsafe or existing report output') from exc
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(canonical(report));f.flush();os.fsync(f.fileno())
    finally:
        pass


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description='GE-03 verified native graph-impact analysis')
    p.add_argument('--repository', required=True)
    p.add_argument('--store', default='.graph-state/scientific')
    p.add_argument('--mode', choices=['candidate','latest-transition'], default='candidate')
    p.add_argument('--knowledge-graph')
    p.add_argument('--output', required=True)
    args = p.parse_args(argv)
    repo = Path(args.repository).resolve(strict=True)
    output = Path(os.path.abspath(args.output))
    if output == repo or repo in output.parents:
        raise GE03Error('Report must be written outside repository')
    result = analyze(repo, mode=args.mode, knowledge_graph=args.knowledge_graph, store=args.store)
    _write_report(output, result)
    sys.stdout.write(json.dumps({k:result[k] for k in ('status','mode','store_generation','review_candidate_count','report_sha256')},sort_keys=True)+'\n')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (GE03Error, GraphStoreError, GraphDomainError, OSError, ValueError, TypeError, KeyError) as e:
        print('GE-03 rejected input: '+str(e),file=sys.stderr)
        sys.exit(2)
