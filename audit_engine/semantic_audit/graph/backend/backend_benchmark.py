"""G6.1: read-only, reproducible benchmarks of existing NetworkX/SciPy adapters.

Separates adapter construction from a common *directed reachability* query.
This is NOT a comparison of full semantic equivalence: SciPy is a sparse
connectivity projection with relation and metadata side channels.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import platform
import random
import statistics
import sys
from time import perf_counter_ns
from typing import Any

import networkx as nx
import numpy as np
import scipy

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph.backend.networkx_adapter import NetworkXAdapter
from audit_engine.semantic_audit.graph.backend.scipy_adapter import SciPyAdapter
from audit_engine.semantic_audit.graph.persistent_domain_state import PersistentDomainGraphStore

SCHEMA = 'g6-backend-benchmark/v1'
MAX_NODES = 10000
MAX_EDGES = 100000
PROFILES = {'smoke': [(16, 55), (64, 260)],
            'standard': [(64, 260), (256, 1024), (768, 3072)]}


class BenchmarkError(ValueError):
    """Failed structural parity, integrity, or benchmark precondition."""


def canonical(obj: Any) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True,
                       separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')


def digest(obj: Any) -> str:
    return sha256(canonical(obj)).hexdigest()


def generate_graph(n: int, e: int, seed: int) -> SemanticGraph:
    """Seeded directed graph; includes cycles, multiedges and self-loops."""
    if type(n) is not int or type(e) is not int or not 1 <= n <= MAX_NODES or not 0 <= e <= MAX_EDGES:
        raise BenchmarkError('Unsafe graph dimensions')
    rng = random.Random(seed)
    ids = [f'n{i:06d}' for i in range(n)]
    nodes = [SemanticNode(node_id=k, entity_type='FEMConcept',
                          attributes={'index': i}, metadata={'origin': 'g6-synthetic'})
             for i, k in enumerate(ids)]
    edges = []
    for i in range(e):
        if i < n:  # cyclic backbone, where edge budget permits
            a, b = i, (i + 1) % n
        elif i % 17 == 0:
            a = b = rng.randrange(n)  # deliberate self-loop
        elif i % 11 == 0 and edges:
            previous = edges[-1]
            a, b = int(previous.source_id[1:]), int(previous.target_id[1:])
        else:
            a, b = rng.randrange(n), rng.randrange(n)
        edges.append(SemanticEdge(ids[a], ids[b], 'DEPENDS_ON',
                                  {'ordinal': i}, {'scenario': 'benchmark'}))
    return SemanticGraph(nodes=nodes, edges=edges)


def _sources(graph: SemanticGraph) -> list[str]:
    ids = [n.node_id for n in graph.nodes]
    return list(dict.fromkeys([ids[0], ids[len(ids)//3], ids[(2*len(ids))//3]]))


def _baseline_reachability(graph: SemanticGraph, source: str) -> set[str]:
    neighbors: dict[str, set[str]] = {n.node_id: set() for n in graph.nodes}
    for edge in graph.edges:
        neighbors[edge.source_id].add(edge.target_id)
    found = {source}
    queue = deque([source])
    while queue:
        for target in neighbors[queue.popleft()]:
            if target not in found:
                found.add(target)
                queue.append(target)
    return found


def _nx_reach(adapter: NetworkXAdapter, source: str) -> set[str]:
    graph = adapter.export()
    return {source, *nx.descendants(graph, source)}


def _sp_reach(adapter: SciPyAdapter, source: str) -> set[str]:
    matrix = adapter.export()
    seen = {adapter.node_to_index[source]}
    queue = deque(seen)
    while queue:
        i = queue.popleft()
        for j in matrix.indices[matrix.indptr[i]:matrix.indptr[i+1]]:
            t = int(j)
            if t not in seen:
                seen.add(t)
                queue.append(t)
    return {adapter.index_to_node[i] for i in seen}


def verify_projection(graph: SemanticGraph, nx_adapter: NetworkXAdapter,
                      sp_adapter: SciPyAdapter) -> dict:
    """Check structure, multiplicities, typed payloads, and common queries."""
    if not graph.nodes:
        raise BenchmarkError('Empty input')
    ids = [n.node_id for n in graph.nodes]
    if len(ids) != len(set(ids)) or len(ids) > MAX_NODES or len(graph.edges) > MAX_EDGES:
        raise BenchmarkError('Duplicate or excessive graph elements')
    if set(ids) != set(nx_adapter.export().nodes) or set(ids) != set(sp_adapter.node_to_index):
        raise BenchmarkError('Node identity mismatch')
    if set(ids) != set(sp_adapter.index_to_node.values()):
        raise BenchmarkError('SciPy reverse mapping mismatch')
    if any(sp_adapter.index_to_node[idx] != name for name, idx in sp_adapter.node_to_index.items()):
        raise BenchmarkError('SciPy identity mapping noninvertible')
    edge_counts = Counter((e.source_id, e.target_id) for e in graph.edges)
    expected_nx = nx_adapter.export()
    actual_nx = Counter((a, b) for a, b in expected_nx.edges())
    if edge_counts != actual_nx:
        raise BenchmarkError('NetworkX directed multiedge parity failure')
    sp_matrix = sp_adapter.export()
    if sp_matrix.shape != (len(ids), len(ids)):
        raise BenchmarkError('Sparse matrix shape mismatch')
    for a, b in edge_counts:
        if sp_matrix[sp_adapter.node_to_index[a], sp_adapter.node_to_index[b]] != edge_counts[(a, b)]:
            raise BenchmarkError('SciPy sparse multiplicity parity failure')
    if int(sp_matrix.sum()) != len(graph.edges):
        raise BenchmarkError('SciPy sparse total edge count mismatch')
    for node in graph.nodes:
        data = expected_nx.nodes[node.node_id]
        if data != {'entity_type': node.entity_type, 'attributes': node.attributes, 'metadata': node.metadata}:
            raise BenchmarkError('NetworkX node payload mismatch')
    original_edges = Counter(canonical({'relation': e.relation_type, 'attributes': e.attributes,
                                        'metadata': e.metadata, 'source': e.source_id,
                                        'target': e.target_id}) for e in graph.edges)
    nx_edges = Counter(canonical({'relation': d['relation'], 'attributes': d['attributes'],
                                  'metadata': d['metadata'], 'source': a, 'target': b})
                       for a, b, d in expected_nx.edges(data=True))
    if original_edges != nx_edges:
        raise BenchmarkError('NetworkX edge metadata not preserved')
    if len(sp_adapter.relations) != len(graph.edges) or len(sp_adapter.metadata['edges']) != len(graph.edges):
        raise BenchmarkError('SciPy side-channel information missing')
    for e, relation, meta in zip(graph.edges, sp_adapter.relations, sp_adapter.metadata['edges']):
        if relation != {'source': e.source_id, 'target': e.target_id,
                        'relation': e.relation_type} or meta != {
                'source': e.source_id, 'target': e.target_id,
                'attributes': e.attributes, 'metadata': e.metadata}:
            raise BenchmarkError('SciPy relation/metadata side-channel parity failure')
    for node in graph.nodes:
        if sp_adapter.metadata['nodes'].get(node.node_id) != {
                'type': node.entity_type, 'attributes': node.attributes,
                'metadata': node.metadata}:
            raise BenchmarkError('SciPy node side-channel parity failure')
    if not nx_adapter.loss_report().get('lossless') or sp_adapter.capabilities().get('lossless') is not False:
        raise BenchmarkError('Misrepresented preservation capabilities')
    queries = []
    for source in _sources(graph):
        baseline = _baseline_reachability(graph, source)
        if baseline != _nx_reach(nx_adapter, source) or baseline != _sp_reach(sp_adapter, source):
            raise BenchmarkError('Directed reachability mismatch')
        queries.append({'source': source, 'reachable': len(baseline),
                        'set_sha256': digest(sorted(baseline))})
    return {'status': 'verified', 'queries': queries,
            'projection_capabilities': {'networkx_lossless': True,
                                        'scipy_sparse_matrix_lossless': False,
                                        'scipy_relation_and_metadata_side_channels': True},
            'multiedge_occurrences': len(graph.edges), 'unique_pairs': len(edge_counts),
            'self_loops': sum(e.source_id == e.target_id for e in graph.edges)}


def _times(fn, *, repeats: int, warmup: int) -> dict:
    for _ in range(warmup):
        fn()
    observations = []
    for _ in range(repeats):
        t0 = perf_counter_ns()
        fn()
        observations.append(max(0, perf_counter_ns() - t0))
    sorted_obs = sorted(observations)
    return {'unit': 'ns', 'observations_ns': observations,
            'median_ns': statistics.median(sorted_obs),
            'p95_ns': sorted_obs[max(0, math.ceil(.95 * len(sorted_obs)) - 1)],
            'minimum_ns': sorted_obs[0], 'maximum_ns': sorted_obs[-1]}


def benchmark_graph(graph: SemanticGraph, *, repeats: int = 7, warmup: int = 2,
                    scenario: str = 'custom') -> dict:
    if type(repeats) is not int or not 3 <= repeats <= 50 or type(warmup) is not int or not 0 <= warmup <= 10:
        raise BenchmarkError('Invalid repetition budget')
    nx_adapter = NetworkXAdapter(graph)
    sp_adapter = SciPyAdapter(graph)
    parity = verify_projection(graph, nx_adapter, sp_adapter)
    sources = _sources(graph)
    timings = {}
    for label, factory, adapter, reach in (
        ('networkx', lambda: NetworkXAdapter(graph), nx_adapter, _nx_reach),
        ('scipy', lambda: SciPyAdapter(graph), sp_adapter, _sp_reach),
    ):
        timings[label] = {
            'projection': _times(factory, repeats=repeats, warmup=warmup),
            'directed_reachability_batch': _times(lambda: [reach(adapter, s) for s in sources],
                                                  repeats=repeats, warmup=warmup),
        }
    csr = sp_adapter.export()
    return {'scenario': scenario, 'graph_sha256': digest(graph.to_dict()),
            'nodes': len(graph.nodes), 'edge_occurrences': len(graph.edges),
            'parity': parity, 'timings': timings,
            'scipy_csr_storage_bytes': int(csr.data.nbytes + csr.indices.nbytes + csr.indptr.nbytes)}


def _load_persisted(repository: Path) -> tuple[SemanticGraph, dict]:
    repository = Path(repository).resolve()
    store = PersistentDomainGraphStore(repository / '.graph-state' / 'scientific')
    state = store.verify()
    if state.get('status') != 'verified':
        raise BenchmarkError('Persisted graph history is not verified')
    view = store.current_view()
    if view is None:
        raise BenchmarkError('No verified persisted graph')
    return view.graph, {'head': state.get('head'), 'generation': state.get('generation'),
                        'snapshot_sha256': state.get('snapshot_sha256'),
                        'graph_fingerprint': view.fingerprint}


def make_report(*, profile: str = 'standard', seed: int = 20261013,
                repeats: int = 7, warmup: int = 2,
                repository: Path | None = None, persisted: bool = False) -> dict:
    if profile not in PROFILES or type(seed) is not int or not 0 <= seed <= 2**32-1:
        raise BenchmarkError('Unknown profile or invalid seed')
    if type(repeats) is not int or not 3 <= repeats <= 50 or type(warmup) is not int or not 0 <= warmup <= 10:
        raise BenchmarkError('Invalid repetition/warmup limits')
    cases = []
    for index, (n, e) in enumerate(PROFILES[profile]):
        cases.append(benchmark_graph(generate_graph(n, e, seed + index),
                                     repeats=repeats, warmup=warmup, scenario=f'synthetic_{n}_{e}'))
    provenance = None
    if persisted:
        if repository is None:
            raise BenchmarkError('Persisted mode needs repository')
        graph, provenance = _load_persisted(repository)
        cases.append(benchmark_graph(graph, repeats=repeats, warmup=warmup,
                                     scenario='verified_ge02_persisted'))
    output = {'schema_version': SCHEMA, 'profile': profile, 'seed': seed,
              'repeats': repeats, 'warmup': warmup, 'cases': cases,
              'persisted_source': provenance,
              'environment': {'python': sys.version.split()[0], 'platform': platform.platform(),
                              'machine': platform.machine(), 'cpu_count': os.cpu_count(),
                              'networkx': nx.__version__, 'scipy': scipy.__version__,
                              'numpy': np.__version__},
              'authority': {'backend_auto_selection_permitted': False,
                            'scientific_truth_established': False,
                            'scientific_approval_permitted': False,
                            'graph_mutation_permitted': False},
              'interpretation': 'Observed single-run timings only; no statistically significant backend winner is claimed.'}
    output['report_sha256'] = digest(output)
    return output


def verify_report(report: dict, *, repository: Path | None = None) -> dict:
    if not isinstance(report, dict) or report.get('schema_version') != SCHEMA:
        raise BenchmarkError('Unknown report schema')
    payload = dict(report)
    submitted_digest = payload.pop('report_sha256', None)
    if submitted_digest != digest(payload):
        raise BenchmarkError('Benchmark report digest mismatch')
    if payload.get('authority') != {'backend_auto_selection_permitted': False,
                                    'scientific_truth_established': False,
                                    'scientific_approval_permitted': False,
                                    'graph_mutation_permitted': False}:
        raise BenchmarkError('Unauthorized benchmark authority')
    if payload.get('profile') not in PROFILES or not isinstance(payload.get('cases'), list):
        raise BenchmarkError('Invalid benchmark manifest')
    if len(payload['cases']) != len(PROFILES[payload['profile']]) + (1 if payload.get('persisted_source') is not None else 0):
        raise BenchmarkError('Unexpected benchmark case count')
    # Independently regenerate deterministic synthetic inputs, their fingerprints,
    # and the reachability answer sets. This detects rehashed source-data forgery.
    for i, (n, e) in enumerate(PROFILES[payload['profile']]):
        graph = generate_graph(n, e, payload['seed'] + i)
        case = payload['cases'][i]
        parity = verify_projection(graph, NetworkXAdapter(graph), SciPyAdapter(graph))
        if (case['scenario'] != f'synthetic_{n}_{e}' or
            case['graph_sha256'] != digest(graph.to_dict()) or
            case['nodes'] != n or case['edge_occurrences'] != e or
            case['parity'] != parity):
            raise BenchmarkError('Rehashed synthetic graph/projection result differs from source')
    if payload.get('persisted_source') is not None:
        if repository is None:
            raise BenchmarkError('Persisted benchmark verification requires source repository')
        graph, source = _load_persisted(repository)
        case = payload['cases'][-1]
        if (payload['persisted_source'] != source or
            case['scenario'] != 'verified_ge02_persisted' or
            case['graph_sha256'] != digest(graph.to_dict()) or
            case['nodes'] != len(graph.nodes) or
            case['edge_occurrences'] != len(graph.edges) or
            case['parity'] != verify_projection(graph, NetworkXAdapter(graph), SciPyAdapter(graph))):
            raise BenchmarkError('Persisted source/projection does not match current verified history')
    for case in payload['cases']:
        if case['parity']['status'] != 'verified':
            raise BenchmarkError('Backend parity not satisfied')
        if case['parity']['projection_capabilities'] != {
            'networkx_lossless': True, 'scipy_sparse_matrix_lossless': False,
            'scipy_relation_and_metadata_side_channels': True}:
            raise BenchmarkError('Backend loss-report semantics have changed')
        for metrics in case['timings'].values():
            for measurement in metrics.values():
                observations = measurement['observations_ns']
                if (measurement['unit'] != 'ns' or len(observations) != report['repeats']
                    or not all(type(x) is int and x >= 0 for x in observations)
                    or measurement['median_ns'] != statistics.median(observations)
                    or measurement['minimum_ns'] != min(observations)
                    or measurement['maximum_ns'] != max(observations)
                    or measurement['p95_ns'] != sorted(observations)[math.ceil(.95 * len(observations)) - 1]):
                    raise BenchmarkError('Inconsistent timing statistics')
    return {'schema_version': SCHEMA, 'status': 'verified',
            'report_sha256': submitted_digest, 'case_count': len(report['cases']),
            'scientific_approval_permitted': False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='G6 manual graph backend benchmark')
    parser.add_argument('command', choices=('run', 'verify'))
    parser.add_argument('--profile', choices=tuple(PROFILES), default='standard')
    parser.add_argument('--seed', type=int, default=20261013)
    parser.add_argument('--repeats', type=int, default=7)
    parser.add_argument('--warmup', type=int, default=2)
    parser.add_argument('--repository', default='.')
    parser.add_argument('--include-persisted', action='store_true')
    parser.add_argument('--report', required=True)
    args = parser.parse_args(argv)
    if args.command == 'run':
        result = make_report(profile=args.profile, seed=args.seed, repeats=args.repeats,
                             warmup=args.warmup, repository=Path(args.repository),
                             persisted=args.include_persisted)
        output = Path(args.report)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(canonical(result))
        print(json.dumps({'status': 'complete', 'report': str(output),
                          'report_sha256': result['report_sha256'],
                          'cases': len(result['cases'])}, sort_keys=True))
    else:
        result = json.loads(Path(args.report).read_bytes())
        print(json.dumps(verify_report(result, repository=Path(args.repository)), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
