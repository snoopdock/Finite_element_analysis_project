"""G7.1: bounded, source-bound structural rule inference over verified scientific graphs.

Reasoning concerns explicit relationship *structure* only. No natural-language
scientific entailment, OWL DL reasoning, autonomous modification or approvals.

Built on GE-01 GraphDomainView and GE-02 verified CAS state; no graph mutation.
"""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

from audit_engine.semantic_audit.graph.domain_integration import (
    GraphDomainError, GraphDomainView, from_scientific_graph, _read_json,
)
from audit_engine.semantic_audit.graph.persistent_domain_state import (
    GraphStoreError, PersistentDomainGraphStore, _input_path, canonical, sha, parse,
)

SCHEMA = 'g7-structural-rule-inference/v1'
RULES = ('G7.R1.SUBCONCEPT_TRANSITIVE', 'G7.R2.PROPOSITION_ANCESTOR_ASSOCIATION')
MAX_NODES = 2000
MAX_EDGES = 12000
MAX_HOPS = 20
MAX_FACTS = 25000
MAX_REPORT_BYTES = 12_000_000


class G7ReasoningError(ValueError):
    """Invalid input, unsafe rule application, or unverifiable inference."""


def _edge_record(e):
    return {'source': e.source_id, 'target': e.target_id, 'relation': e.relation_type,
            'attributes': e.attributes, 'metadata': e.metadata}


def _reference(edge):
    """Exact edge content (including metadata) binds each witness to a source fact."""
    return sha(canonical(_edge_record(edge)))


def _validate(view: GraphDomainView):
    if not isinstance(view, GraphDomainView) or view.domain != 'scientific_knowledge':
        raise G7ReasoningError('G7.1 accepts only a scientific_knowledge graph view')
    snap = view.snapshot()  # fingerprinted, deterministic GE-01 canonical view
    graph = view.graph
    if len(graph.nodes) > MAX_NODES or len(graph.edges) > MAX_EDGES:
        raise G7ReasoningError('Reasoning graph exceeds configured resource budget')
    kinds = {}
    for node in graph.nodes:
        if not isinstance(node.node_id, str) or not node.node_id or node.node_id in kinds:
            raise G7ReasoningError('Duplicate/invalid graph entity identity')
        kinds[node.node_id] = node.entity_type
    for edge in graph.edges:
        if edge.source_id not in kinds or edge.target_id not in kinds:
            raise G7ReasoningError('Dangling source graph edge')
        if edge.relation_type == 'SUBCONCEPT_OF':
            if kinds[edge.source_id] != 'ScientificConcept' or kinds[edge.target_id] != 'ScientificConcept':
                raise G7ReasoningError('SUBCONCEPT_OF requires concept-to-concept endpoints')
        elif edge.relation_type == 'HAS_CONCEPT':
            if kinds[edge.source_id] != 'ScientificProposition' or kinds[edge.target_id] != 'ScientificConcept':
                raise G7ReasoningError('HAS_CONCEPT requires proposition-to-concept endpoints')
    return snap, kinds


def _hierarchy(graph):
    """Canonical direct concept relations, preserving one verifiable edge witness."""
    parents = defaultdict(dict)
    direct_propositions = defaultdict(dict)
    for edge in graph.edges:
        if edge.relation_type == 'SUBCONCEPT_OF':
            cache = parents[edge.source_id]
        elif edge.relation_type == 'HAS_CONCEPT':
            cache = direct_propositions[edge.source_id]
        else:
            continue  # No other predicate ever participates in these rule semantics.
        ref = _reference(edge)
        old = cache.get(edge.target_id)
        if old is None or ref < old:
            cache[edge.target_id] = ref
    return parents, direct_propositions


def _ancestors(start, parents):
    """Shortest deterministic witnessed paths, never silently truncate closure."""
    paths = {start: (start,)}
    traces = {start: ()}
    q = deque([start])
    while q:
        node = q.popleft()
        path = paths[node]
        for parent, witness in sorted(parents.get(node, {}).items()):
            if parent == start or parent in path:
                raise G7ReasoningError('Cyclic concept hierarchy is not permitted')
            if parent in paths:
                continue
            if len(path) > MAX_HOPS:
                raise G7ReasoningError('Concept ancestry exceeds complete inference budget')
            paths[parent] = path + (parent,)
            traces[parent] = traces[node] + (witness,)
            q.append(parent)
    return paths, traces


def reason(view: GraphDomainView, *, store_head: str | None = None) -> dict[str, Any]:
    """Generate complete bounded structural closure with explicit edge witnesses."""
    snapshot, kinds = _validate(view)
    parents, direct_props = _hierarchy(view.graph)
    concepts = sorted(n for n, typ in kinds.items() if typ == 'ScientificConcept')
    propositions = sorted(n for n, typ in kinds.items() if typ == 'ScientificProposition')
    inference = []
    ancestry = {}
    for concept in concepts:
        ancestry[concept] = _ancestors(concept, parents)
        paths, traces = ancestry[concept]
        for ancestor in sorted(paths):
            path = paths[ancestor]
            if len(path) < 3 or ancestor in parents.get(concept, {}):
                continue
            inference.append({
                'rule_id': RULES[0], 'source_id': concept, 'target_id': ancestor,
                'inferred_relation': 'SUBCONCEPT_OF',
                'path_node_ids': list(path), 'supporting_edge_sha256s': list(traces[ancestor]),
                'structural_inference_only': True,
            })
    for proposition in propositions:
        observed = direct_props.get(proposition, {})
        for concept, proposition_edge_hash in sorted(observed.items()):
            paths, traces = ancestry[concept]
            for ancestor in sorted(paths):
                if ancestor == concept:
                    continue
                inference.append({
                    'rule_id': RULES[1], 'source_id': proposition,
                    'target_id': ancestor, 'inferred_relation': 'HAS_ANCESTOR_CONCEPT',
                    'path_node_ids': [proposition] + list(paths[ancestor]),
                    'supporting_edge_sha256s': [proposition_edge_hash] + list(traces[ancestor]),
                    'structural_inference_only': True,
                })
    if len(inference) > MAX_FACTS:
        raise G7ReasoningError('Inference closure exceeds configured resource budget')
    inference.sort(key=lambda f: (f['rule_id'], f['source_id'], f['target_id'],
                                   f['path_node_ids'], f['supporting_edge_sha256s']))
    # Multiple direct association routes may derive the same fact. Retain the
    # lexicographically earliest canonical witnessed path, never inflate counts.
    unique = {}
    for item in inference:
        key = item['rule_id'], item['source_id'], item['target_id']
        unique.setdefault(key, item)
    output = {
        'schema_version': SCHEMA,
        'rule_ids': list(RULES),
        'source_domain': view.domain,
        'source_graph_fingerprint': view.fingerprint,
        'source_snapshot_sha256': snapshot['snapshot_sha256'],
        'source_input_sha256': view.input_sha256,
        'source_store_head_sha256': store_head,
        'source_node_count': len(view.graph.nodes),
        'source_edge_occurrence_count': len(view.graph.edges),
        'inferences': list(unique.values()),
        'inference_count': len(unique),
        'status': 'verified_source_structural_inference_only',
        'bounds': {'max_hops': MAX_HOPS, 'max_nodes': MAX_NODES,
                   'max_edges': MAX_EDGES, 'max_facts': MAX_FACTS},
        'authority': {'scientific_truth_established': False,
                      'owl_dl_entailment_established': False,
                      'automatic_approval_permitted': False,
                      'authoritative_graph_mutation_permitted': False},
    }
    if len(canonical(output)) > MAX_REPORT_BYTES:
        raise G7ReasoningError('Inference report exceeds byte budget')
    output['report_sha256'] = sha(canonical(output))
    return output


def verify_reasoning(view: GraphDomainView, report: Any, *, store_head: str | None = None):
    """Independent exact replay: recompute proofs and closure, not only a digest."""
    if not isinstance(report, dict):
        raise G7ReasoningError('Expected JSON report object')
    expected = reason(view, store_head=store_head)
    if report != expected:
        raise G7ReasoningError('Source-bound reasoning report mismatch')
    return {'status': 'verified', 'rule_count': len(RULES),
            'inference_count': expected['inference_count'],
            'report_sha256': expected['report_sha256'],
            'source_snapshot_sha256': expected['source_snapshot_sha256']}


def _read_bounded_json(path: Path):
    if path.is_symlink():
        raise G7ReasoningError('Symlinked report input forbidden')
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    try:
        stat_info = os.fstat(fd)
        if not stat.S_ISREG(stat_info.st_mode) or stat_info.st_size > MAX_REPORT_BYTES:
            raise G7ReasoningError('Report must be a bounded regular file')
        data = os.read(fd, MAX_REPORT_BYTES + 1)
        if len(data) != stat_info.st_size:
            raise G7ReasoningError('Report changed during read')
        return parse(data)
    finally:
        os.close(fd)


def _load_view(repo: Path, *, mode: str, knowledge_graph: str | None, store: str):
    if mode == 'candidate':
        if knowledge_graph is None:
            raise G7ReasoningError('Candidate mode requires --knowledge-graph')
        source_path = _input_path(repo, knowledge_graph)
        return from_scientific_graph(_read_json(source_path)), None
    if mode == 'persisted':
        if knowledge_graph is not None:
            raise G7ReasoningError('Persisted mode does not accept --knowledge-graph')
        location = Path(store)
        if (location.is_absolute() or '..' in location.parts or
                location.parts[:1] != ('.graph-state',) or len(location.parts) < 2):
            raise G7ReasoningError('Store must be beneath .graph-state')
        store_path = repo / location
        if any(p.is_symlink() for p in (store_path, *store_path.parents)):
            raise G7ReasoningError('Symlinked graph store forbidden')
        engine = PersistentDomainGraphStore(store_path)
        state = engine.verify()
        if state.get('status') != 'verified' or state.get('domain') != 'scientific_knowledge':
            raise G7ReasoningError('GE-02 verified scientific history required')
        view = engine.current_view()
        if view is None:
            raise G7ReasoningError('Missing verified graph state')
        return view, state['head']
    raise G7ReasoningError('Unsupported graph source mode')


def _write_new(path: Path, data: dict):
    """Detached, exclusive report publication; never overwrite existing evidence."""
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise G7ReasoningError('Symlinked report destination forbidden')
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical(data)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())


def main(argv=None):
    p = argparse.ArgumentParser(description='G7.1 source-bound structural reasoning')
    p.add_argument('action', choices=('run', 'verify'))
    p.add_argument('--repository', required=True)
    p.add_argument('--mode', choices=('persisted', 'candidate'), default='persisted')
    p.add_argument('--knowledge-graph')
    p.add_argument('--store', default='.graph-state/scientific')
    p.add_argument('--report', required=True)
    options = p.parse_args(argv)
    repo = Path(options.repository).resolve(strict=True)
    if not repo.is_dir():
        raise G7ReasoningError('Repository must be a directory')
    path = Path(os.path.abspath(options.report))
    if path == repo or repo in path.parents:
        raise G7ReasoningError('Detached report path must be outside the repository')
    view, head = _load_view(repo, mode=options.mode, knowledge_graph=options.knowledge_graph,
                            store=options.store)
    if options.action == 'run':
        result = reason(view, store_head=head)
        _write_new(path, result)
        summary = {'status': result['status'], 'inference_count': result['inference_count'],
                   'report_sha256': result['report_sha256']}
    else:
        summary = verify_reasoning(view, _read_bounded_json(path), store_head=head)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (G7ReasoningError, GraphStoreError, GraphDomainError, OSError, ValueError, TypeError) as exc:
        sys.stderr.write('G7.1 validation failed: ' + str(exc) + '\n')
        sys.exit(2)
