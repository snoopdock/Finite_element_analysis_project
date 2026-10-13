"""G7.2: verified, read-only semantic inference lifecycle over GE-02 graph changes.

This is a reconciliation of G7.1's bounded *structural* closure on two independently
verified graph versions. Retraction means removal from structural closure, not
rejection of a scientific proposition; no graph or document mutation is allowed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

from audit_engine.semantic_audit.graph.domain_integration import (
    GraphDomainError, GraphDomainView, from_scientific_graph, _read_json,
)
from audit_engine.semantic_audit.graph.persistent_domain_state import (
    GraphStoreError, PersistentDomainGraphStore, _input_path, _strict_view,
    _transition, canonical, sha,
)
from audit_engine.semantic_audit.graph.structural_reasoning import (
    G7ReasoningError, reason, _read_bounded_json, _write_new,
)

SCHEMA = 'g7-reasoning-change-review/v1'
MAX_REPORT_BYTES = 12_000_000
MAX_CHANGED_FACTS = 50000

class G72Error(ValueError):
    """A source or inference-transition is invalid or untrustworthy."""


def _safe_store(repo: Path, name: str) -> Path:
    relative = Path(name)
    if (relative.is_absolute() or '..' in relative.parts or
            relative.parts[:1] != ('.graph-state',) or len(relative.parts) < 2):
        raise G72Error('Store must be underneath .graph-state/')
    path = repo / relative
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise G72Error('Symlinked graph-state directories forbidden')
    return path


def _key(fact: dict) -> tuple[str, str, str, str]:
    return (fact['rule_id'], fact['source_id'], fact['inferred_relation'], fact['target_id'])


def review_views(before: GraphDomainView, after: GraphDomainView, *,
                 mode: str, head_sha256: str, store_generation: int,
                 previous_commit_sha256: str | None = None,
                 persisted_transition: dict | None = None) -> dict[str, Any]:
    """Recompute both finite rule closures, reconcile facts and exact witness changes."""
    if before.domain != 'scientific_knowledge' or after.domain != 'scientific_knowledge':
        raise G72Error('Only scientific_knowledge graph transitions may be reviewed')
    if mode not in ('candidate', 'latest-transition'):
        raise G72Error('Unsupported comparison mode')
    if not isinstance(head_sha256, str) or len(head_sha256) != 64:
        raise G72Error('Verified GE-02 HEAD required')
    previous = reason(before)
    proposed = reason(after)
    delta = _transition(before, after)
    if delta is None or delta.get('schema_version') != 'ge02-graph-transition/v1':
        raise G72Error('Native GE-02 transition is required')
    if persisted_transition is not None and persisted_transition != delta:
        raise G72Error('Persisted GE-02 transition and independently replayed delta disagree')
    b = {_key(f): f for f in previous['inferences']}
    a = {_key(f): f for f in proposed['inferences']}
    if len(b) != previous['inference_count'] or len(a) != proposed['inference_count']:
        raise G72Error('Ambiguous duplicate rule facts')
    added_keys = a.keys() - b.keys()
    removed_keys = b.keys() - a.keys()
    common = a.keys() & b.keys()
    changed_proofs = sorted(k for k in common if a[k] != b[k])
    if len(added_keys) + len(removed_keys) + len(changed_proofs) > MAX_CHANGED_FACTS:
        raise G72Error('Reasoning-review change budget exceeded')
    added = [a[k] for k in sorted(added_keys)]
    retracted = [b[k] for k in sorted(removed_keys)]
    rewitnessed = [{'fact': {'rule_id': k[0], 'source_id': k[1],
                             'inferred_relation': k[2], 'target_id': k[3]},
                    'before': b[k], 'after': a[k]}
                   for k in changed_proofs]
    # Structural review candidates come from the same native GE-02 comparison.
    structural = delta['impact']
    if (structural.get('status') != 'review_candidates_only' or
            structural.get('automatic_approval_permitted') is not False or
            structural.get('scientific_truth_established') is not False):
        raise G72Error('GE-02 impact report crosses an authority boundary')
    if delta['graph_delta']['is_noop']:
        if added or retracted or rewitnessed or structural['review_candidates']:
            raise G72Error('No-op transition cannot change reasoning closure')
        status = 'no_structural_change'
    elif added or retracted or rewitnessed:
        status = 'inference_review_required'
    else:
        status = 'graph_changed_inferences_unchanged'
    if mode == 'latest-transition' and previous_commit_sha256 is None:
        # No historical transition: a generation-1 head has no predecessor.
        if not delta['graph_delta']['is_noop']:
            raise G72Error('No historical predecessor cannot imply a change')
        status = 'no_prior_transition'
    output = {
        'schema_version': SCHEMA,
        'mode': mode,
        'status': status,
        'verified_store_head_sha256': head_sha256,
        'verified_store_generation': store_generation,
        'historical_parent_commit_sha256': previous_commit_sha256,
        'domain': 'scientific_knowledge',
        'before_snapshot_sha256': previous['source_snapshot_sha256'],
        'after_snapshot_sha256': proposed['source_snapshot_sha256'],
        'before_graph_fingerprint': previous['source_graph_fingerprint'],
        'after_graph_fingerprint': proposed['source_graph_fingerprint'],
        'before_input_sha256': previous['source_input_sha256'],
        'after_input_sha256': proposed['source_input_sha256'],
        'before_reasoning_sha256': previous['report_sha256'],
        'after_reasoning_sha256': proposed['report_sha256'],
        'rules': previous['rule_ids'],
        'before_inference_count': len(b),
        'after_inference_count': len(a),
        'added_inferences': added,
        'retracted_inferences': retracted,
        'rewitnessed_inferences': rewitnessed,
        'unchanged_inference_count': len(common) - len(changed_proofs),
        'native_graph_delta_id': delta['graph_delta']['delta_id'],
        'native_graph_delta_is_noop': delta['graph_delta']['is_noop'],
        'structural_review_candidates': structural['review_candidates'],
        'structural_review_candidate_count': len(structural['review_candidates']),
        'limits': {'max_changed_facts': MAX_CHANGED_FACTS,
                   'max_report_bytes': MAX_REPORT_BYTES},
        'authority': {
            'scientific_truth_established': False,
            'owl_dl_entailment_established': False,
            'automatic_approval_permitted': False,
            'authoritative_graph_mutation_permitted': False,
            'automatic_document_edits_permitted': False,
        },
    }
    raw = canonical(output)
    if len(raw) > MAX_REPORT_BYTES:
        raise G72Error('Reasoning change report exceeds byte budget')
    output['report_sha256'] = sha(raw)
    return output


def analyze(repo: str | Path, *, mode: str = 'candidate',
            knowledge_graph: str | None = None,
            store: str = '.graph-state/scientific') -> dict[str, Any]:
    repo = Path(repo).resolve(strict=True)
    if not repo.is_dir():
        raise G72Error('Missing repository directory')
    state_store = PersistentDomainGraphStore(_safe_store(repo, store))
    state = state_store.verify()  # all reachable commits and transitions
    if state.get('status') != 'verified' or state.get('domain') != 'scientific_knowledge':
        raise G72Error('Verified scientific GE-02 baseline required')
    baseline = state_store.current_view()
    if baseline is None:
        raise G72Error('Verified store contains no graph')
    if mode == 'candidate':
        if not knowledge_graph:
            raise G72Error('Candidate mode requires --knowledge-graph')
        path = _input_path(repo, knowledge_graph)
        candidate = from_scientific_graph(_read_json(path))
        return review_views(baseline, candidate, mode=mode,
                            head_sha256=state['head'], store_generation=state['generation'])
    if mode == 'latest-transition':
        if knowledge_graph is not None:
            raise G72Error('latest-transition mode forbids --knowledge-graph')
        if state['generation'] == 1:
            return review_views(baseline, baseline, mode=mode,
                                head_sha256=state['head'], store_generation=1)
        receipt = state_store._cas_read('commits', state['head'])
        parent_id = receipt['parent_receipt_sha256']
        parent = state_store._cas_read('commits', parent_id)
        previous = _strict_view(state_store._cas_read('objects', parent['snapshot_object_sha256']))
        recorded = state_store._cas_read('transitions', receipt['transition_object_sha256'])
        return review_views(previous, baseline, mode=mode,
                            head_sha256=state['head'], store_generation=state['generation'],
                            previous_commit_sha256=parent_id, persisted_transition=recorded)
    raise G72Error('Unsupported reasoning-change mode')


def verify(repo: str | Path, report: Any, *, mode: str = 'candidate',
           knowledge_graph: str | None = None,
           store: str = '.graph-state/scientific') -> dict[str, Any]:
    if not isinstance(report, dict):
        raise G72Error('Expected JSON object report')
    expected = analyze(repo, mode=mode, knowledge_graph=knowledge_graph, store=store)
    if expected != report:
        raise G72Error('Source-bound reasoning-change report mismatch')
    return {
        'status': 'verified', 'review_status': expected['status'],
        'added_inference_count': len(expected['added_inferences']),
        'retracted_inference_count': len(expected['retracted_inferences']),
        'rewitnessed_inference_count': len(expected['rewitnessed_inferences']),
        'unchanged_inference_count': expected['unchanged_inference_count'],
        'report_sha256': expected['report_sha256'],
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='G7.2 verified reasoning lifecycle review')
    p.add_argument('action', choices=('run', 'verify'))
    p.add_argument('--repository', required=True)
    p.add_argument('--mode', choices=('candidate', 'latest-transition'), default='candidate')
    p.add_argument('--knowledge-graph')
    p.add_argument('--store', default='.graph-state/scientific')
    p.add_argument('--report', required=True)
    o = p.parse_args(argv)
    repo = Path(o.repository).resolve(strict=True)
    output = Path(os.path.abspath(o.report))
    if output == repo or repo in output.parents:
        raise G72Error('Report must be detached from the checked-out repository')
    args = dict(mode=o.mode, knowledge_graph=o.knowledge_graph, store=o.store)
    if o.action == 'run':
        result = analyze(repo, **args)
        _write_new(output, result)
        summary = {'status': result['status'],
                   'added_inference_count': len(result['added_inferences']),
                   'retracted_inference_count': len(result['retracted_inferences']),
                   'rewitnessed_inference_count': len(result['rewitnessed_inferences']),
                   'report_sha256': result['report_sha256']}
    else:
        summary = verify(repo, _read_bounded_json(output), **args)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (G72Error, GraphStoreError, GraphDomainError, G7ReasoningError,
            OSError, ValueError, TypeError, KeyError) as exc:
        sys.stderr.write('G7.2 review rejected: ' + str(exc) + '\n')
        sys.exit(2)
