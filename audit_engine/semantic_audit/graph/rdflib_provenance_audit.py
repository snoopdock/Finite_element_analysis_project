"""RI-03: source-bound RDF provenance, cross-context consistency and timings.

Derived read-only view. No arbitrary SPARQL, remote graphs, writeback,
scientific approval, or OWL entailment. Verification REBUILDS the source.
Timing observations are environmental measurements, not reproducible proofs.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
from statistics import median
from time import perf_counter_ns
from typing import Any

from rdflib import Literal, URIRef
from rdflib.namespace import RDF, XSD

from audit_engine.semantic_audit.graph import rdflib_query_layer as ri01
from audit_engine.semantic_audit.graph import rdflib_scientific_index as ri02
from audit_engine.semantic_audit.graph.persistent_domain_state import canonical

SCHEMA = 'ri03-provenance-audit-benchmark/v1'
MAX_REPEATS = 7
MAX_ROWS = 100
MAX_TIMINGS_NS = 3_600_000_000_000  # bounded input size, not a runtime promise
QUERIES = ('sources_for_proposition', 'propositions_citing_source',
           'concept_evidence_paths', 'relations_with_unverified_support')
LIMITATIONS = {
    'scientific_truth_established': False,
    'semantic_entailment_verified': False,
    'automatic_approval_permitted': False,
    'authoritative_mutation_permitted': False,
    'arbitrary_sparql_permitted': False,
    'timings_are_cryptographic_proofs': False,
}


class ProvenanceAuditError(ri02.ScientificIndexError):
    """Invalid cross-context claims, detached artifact or unsafe query."""


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _subject(graph, subject, predicate):
    values = list(graph.objects(subject, predicate))
    if len(values) != 1:
        raise ProvenanceAuditError('Expected exactly one source-bound RDF value')
    return values[0]


def _graph_quads(index):
    return sum(len(index.dataset.graph(ctx)) for ctx in index.contexts)


def audit_index(index: ri02.ScientificIndex) -> dict:
    """Reconcile RI-01/02 named contexts with *verified* G4 occurrences.

    The source is the RI-02 verified index, built after G4.6 replay. This is a
    second, separately implemented cross-context check, not a claim of
    adversarial independence from RDFLib or the installed Python environment.
    """
    ds = index.dataset
    asserted, fields, provenance, scientific, vocab = (ds.graph(x) for x in index.contexts)
    view = index.base.source_view
    snap = ri01._uri('snapshot', view.fingerprint)
    contains_node = ri01._uri('property', 'containsNode')
    contains_edge = ri01._uri('property', 'containsEdge')
    nodes = set(asserted.objects(snap, contains_node))
    statements = set(asserted.objects(snap, contains_edge))
    expected_nodes = {ri01._uri('node', x.node_id) for x in view.graph.nodes}
    if nodes != expected_nodes or len(statements) != len(view.graph.edges):
        raise ProvenanceAuditError('G4 source membership mismatch')
    if not all(isinstance(x, URIRef) for x in nodes | statements):
        raise ProvenanceAuditError('Non-IRI G4 semantic identity')
    if nodes & statements:
        raise ProvenanceAuditError('Node/statement IRI identity collision')

    # Reconstruct the exact allowed scientific scalar index from G4 statements
    # and the original source nodes, independent of the RI-02 index contents.
    expected_index = set()
    for node in view.graph.nodes:
        resource = ri01._uri('node', node.node_id)
        if _subject(asserted, resource, ri01._uri('property', 'nodeIdentifier')) != Literal(node.node_id):
            raise ProvenanceAuditError('G4 node identity mismatch')
        if _subject(asserted, resource, ri01._uri('property', 'entityType')) != Literal(node.entity_type):
            raise ProvenanceAuditError('G4 node type mismatch')
        for payload, vocabulary in ((node.attributes, ri02.NODE_ATTRIBUTES),
                                    (node.metadata, ri02.NODE_METADATA)):
            for field, (name, expected) in vocabulary.items():
                if field in payload:
                    expected_index.add((resource, ri02._indexed(name), ri02._typed(payload[field], expected)))
    for statement in statements:
        if _subject(asserted, statement, RDF.type) != RDF.Statement:
            raise ProvenanceAuditError('Missing G4 reification type')
        src = _subject(asserted, statement, RDF.subject)
        dst = _subject(asserted, statement, RDF.object)
        if src not in nodes or dst not in nodes:
            raise ProvenanceAuditError('Reified edge has dangling endpoint')
        occurrence = _subject(asserted, statement, ri01._uri('property', 'parallelEdgeOccurrence'))
        if (not isinstance(occurrence, Literal) or
                occurrence.datatype != XSD.nonNegativeInteger or int(occurrence) < 0):
            raise ProvenanceAuditError('Malformed G4 edge occurrence number')
        # The RI-02 source-G4 edge multiplicity reconciliation already checks
        # that no statement is invented, missing or assigned the wrong source.
        for field_name, vocab_spec in (('attributesJson', ri02.EDGE_ATTRIBUTES),
                                       ('metadataJson', ri02.EDGE_METADATA)):
            payload = ri02._g4_dict(asserted, statement, field_name)
            for field, (name, expected) in vocab_spec.items():
                if field in payload:
                    expected_index.add((statement, ri02._indexed(name), ri02._typed(payload[field], expected)))
    if set(scientific) != expected_index:
        raise ProvenanceAuditError('Scientific scalar index is inconsistent with G4 source')
    if any(subject not in nodes | statements for subject, _, _ in scientific):
        raise ProvenanceAuditError('Scientific index contains an orphan resource')

    # RI-01's base contexts must be preserved byte-for-byte as RDF quad sets.
    for ctx in index.contexts[:3]:
        if set(ds.graph(ctx)) != set(index.base.dataset.graph(ctx)):
            raise ProvenanceAuditError('RI-01 base RDF context altered')
    if ri01._nq(ds, index.contexts[:3]) != index.base.nquads:
        raise ProvenanceAuditError('RI-01 canonical RDF serialization mismatch')
    if not vocab or _graph_quads(index) != len(set(ds.quads((None,None,None,None)))):
        raise ProvenanceAuditError('Named RDF context or quad count mismatch')
    if ri01._nq(ds, index.contexts) != index.nquads:
        raise ProvenanceAuditError('RI-02 canonical dataset changed')

    # All provenance fields and restrictive authority flags are verified.
    source = ri01._uri('query-view', view.snapshot()['snapshot_sha256'])
    for key, value in index.base.provenance.items():
        if value is not None and _subject(provenance, source, ri01._uri('query-provenance', key)) != ri01._literal(value):
            raise ProvenanceAuditError('Source provenance mismatch')
    for key in ('scientific_truth_established', 'semantic_entailment_verified',
                'automatic_approval_permitted', 'authoritative_mutation_permitted'):
        if _subject(provenance, source, ri01._uri('query-provenance', key)) != Literal(False, datatype=XSD.boolean):
            raise ProvenanceAuditError('RDF authority flag is not false')
    for name, expected in (('source_node_count', len(nodes)),
                           ('source_edge_occurrence_count', len(statements)),
                           ('indexed_scalar_triple_count', len(expected_index)),
                           ('vocabulary_triple_count', len(vocab)),
                           ('asserted_g4_triple_count', len(asserted))):
        if index.projection_counts[name] != expected:
            raise ProvenanceAuditError('RI-02 projection count mismatch')

    type_of = ri01._uri('property', 'entityType')
    by_type = Counter(str(_subject(asserted, n, type_of)) for n in nodes)
    rel_prop = ri01._uri('property', 'relationType')
    by_relation = Counter(str(_subject(asserted, s, rel_prop)) for s in statements)
    # Report only *declared* flags. Absence is not an assertion of falsity.
    unverified = sum((s, ri02._indexed('scientificSupportVerifiedFlag'),
                      Literal(False, datatype=XSD.boolean)) in scientific for s in statements)
    return {
        'node_count': len(nodes), 'edge_occurrence_count': len(statements),
        'named_graph_count': len(index.contexts), 'total_quads': _graph_quads(index),
        'indexed_scalar_triples': len(expected_index),
        'node_type_counts': dict(sorted(by_type.items())),
        'relation_occurrence_counts': dict(sorted(by_relation.items())),
        'explicit_scientific_support_false_count': unverified,
        'source_graph_fingerprint': view.fingerprint,
        'source_snapshot_sha256': view.snapshot()['snapshot_sha256'],
        'source_input_sha256': view.input_sha256,
        'g4_manifest_sha256': index.base.g4_manifest['manifest_sha256'],
        'ri01_nquads_sha256': _digest(index.base.nquads),
        'ri02_nquads_sha256': _digest(index.nquads),
        'status': 'consistent',
    }


def _query(index: ri02.ScientificIndex, query_id: str, argument: str, limit: int) -> list[dict]:
    if query_id not in QUERIES or not isinstance(argument, str) or not argument or len(argument) > 4096:
        raise ProvenanceAuditError('Only fixed bounded provenance queries are permitted')
    if type(limit) is not int or not 1 <= limit <= MAX_ROWS:
        raise ProvenanceAuditError('Invalid bounded query limit')
    a, i = index.contexts[0].n3(), index.contexts[3].n3()
    snap = ri01._uri('snapshot', index.base.source_view.fingerprint).n3()
    cp, ce = (ri01._uri('property', k).n3() for k in ('containsNode','containsEdge'))
    relation, ordinal = (ri01._uri('property', k).n3() for k in ('relationType','parallelEdgeOccurrence'))
    node_iri = ri01._uri('node', argument)
    bind = {'wanted': node_iri}
    if query_id == 'sources_for_proposition':
        body = f'''{snap} {ce} ?citation .
          ?citation {RDF.subject.n3()} ?wanted ; {RDF.object.n3()} ?sourceRef ;
                    {relation} "CITES_SOURCE" ; {ordinal} ?occurrence .'''
        cols = '?citation ?sourceRef ?occurrence'
        clauses = f'GRAPH {a} {{ {body} }}'
    elif query_id == 'propositions_citing_source':
        body = f'''{snap} {ce} ?citation .
          ?citation {RDF.subject.n3()} ?proposition ; {RDF.object.n3()} ?wanted ;
                    {relation} "CITES_SOURCE" ; {ordinal} ?occurrence .'''
        cols = '?citation ?proposition ?occurrence'
        clauses = f'GRAPH {a} {{ {body} }}'
    elif query_id == 'concept_evidence_paths':
        cols = '?proposition ?conceptLink ?citation ?sourceRef ?conceptOccurrence ?citationOccurrence'
        clauses = f'''GRAPH {a} {{
          {snap} {ce} ?conceptLink, ?citation .
          ?conceptLink {RDF.subject.n3()} ?proposition ; {RDF.object.n3()} ?wanted ;
                       {relation} "HAS_CONCEPT" ; {ordinal} ?conceptOccurrence .
          ?citation {RDF.subject.n3()} ?proposition ; {RDF.object.n3()} ?sourceRef ;
                     {relation} "CITES_SOURCE" ; {ordinal} ?citationOccurrence . }}'''
    else:  # relations_with_unverified_support
        cols = '?statement ?target ?occurrence ?flag'
        clauses = f'''GRAPH {a} {{ {snap} {ce} ?statement .
          ?statement {RDF.subject.n3()} ?wanted ; {RDF.object.n3()} ?target ;
                     {ordinal} ?occurrence . }}
          GRAPH {i} {{ ?statement {ri02._indexed('scientificSupportVerifiedFlag').n3()} ?flag . }}
          FILTER(?flag = false)'''
    sparql = f'SELECT {cols} WHERE {{ {clauses} }} ORDER BY {cols} LIMIT {limit}'
    try:
        response = index.dataset.query(sparql, initBindings=bind)
        result = [{str(key): ri01._term(value) for key,value in row.asdict().items()}
                  for row in response]
    except Exception as exc:
        raise ProvenanceAuditError('Fixed provenance SPARQL query failed') from exc
    if len(result) > limit:
        raise ProvenanceAuditError('SPARQL escaped fixed query result limit')
    return result


def provenance_query(index, query_id: str, argument: str, limit: int = 100) -> list[dict]:
    """Run a non-authoritative query after structural consistency checking."""
    audit_index(index)
    return _query(index, query_id, argument, limit)


def _timed(call, repeats: int) -> dict:
    readings = []
    for _ in range(repeats):
        start = perf_counter_ns()
        call()
        elapsed = perf_counter_ns() - start
        if not 0 <= elapsed <= MAX_TIMINGS_NS:
            raise ProvenanceAuditError('Timer produced invalid measurement')
        readings.append(elapsed)
    return {'samples_ns': readings, 'median_ns': median(readings),
            'min_ns': min(readings), 'max_ns': max(readings)}


def _benchmark(view, state, query_id, argument, limit, repeats):
    # One warm-up avoids measuring the initial RDFLib SPARQL parser import cost.
    warm = ri02.build_scientific_index(view, store_state=state)
    audit_index(warm)
    _query(warm, query_id, argument, limit)
    build = _timed(lambda: ri02.build_scientific_index(view, store_state=state), repeats)
    verify = _timed(lambda: audit_index(warm), repeats)
    query = _timed(lambda: _query(warm, query_id, argument, limit), repeats)
    return {'repeats': repeats, 'warmup_executed': True,
            'measurements': {'build_index': build, 'cross_context_audit': verify,
                             'bounded_sparql_query': query},
            'interpretation': 'Descriptive environment-dependent timings only; no backend ranking'}


def _report_core(index, *, mode, query_id, argument, limit):
    consistency = audit_index(index)
    results = _query(index, query_id, argument, limit)
    return {
        'schema_version': SCHEMA, 'mode': mode,
        'query_id': query_id, 'query_argument': argument, 'query_limit': limit,
        'results': results, 'result_count': len(results), 'consistency': consistency,
        'named_contexts': [str(c) for c in index.contexts],
        'dataset_nquads_sha256': _digest(index.nquads),
        'source_verification': 'G4.6 verified; RI-01/RI-02 replay; RI-03 cross-context audit',
        **LIMITATIONS,
    }


def build_report(repository: Path, *, mode: str, knowledge_graph: str | None,
                 query_id: str, argument: str, limit: int = 100,
                 repeats: int = 3) -> tuple[dict, bytes]:
    if type(repeats) is not int or not 1 <= repeats <= MAX_REPEATS:
        raise ProvenanceAuditError('Benchmark repeats must be 1 to 7')
    if query_id not in QUERIES or not isinstance(argument, str) or not argument or len(argument) > 4096:
        raise ProvenanceAuditError('Invalid fixed provenance query')
    if type(limit) is not int or not 1 <= limit <= MAX_ROWS:
        raise ProvenanceAuditError('Query limit must be 1 to 100')
    view, state = ri01.resolve_view(repository, mode=mode, knowledge_graph=knowledge_graph)
    index = ri02.build_scientific_index(view, store_state=state)
    report = _report_core(index, mode=mode, query_id=query_id, argument=argument, limit=limit)
    report['benchmark'] = _benchmark(view, state, query_id, argument, limit, repeats)
    report['report_sha256'] = _digest(canonical(report))
    if len(canonical(report)) > ri01.MAX_REPORT_BYTES:
        raise ProvenanceAuditError('RI-03 report exceeds detached report limit')
    return report, index.nquads


def _timing_shape(benchmark):
    if not isinstance(benchmark, dict) or type(benchmark.get('repeats')) is not int:
        raise ProvenanceAuditError('Invalid benchmark envelope')
    repetitions = benchmark['repeats']
    if repetitions < 1 or repetitions > MAX_REPEATS or benchmark.get('warmup_executed') is not True:
        raise ProvenanceAuditError('Invalid benchmark repetition count')
    if benchmark.get('interpretation') != 'Descriptive environment-dependent timings only; no backend ranking':
        raise ProvenanceAuditError('Benchmark scientific interpretation was changed')
    samples = benchmark.get('measurements')
    if not isinstance(samples, dict) or set(samples) != {
        'build_index', 'cross_context_audit', 'bounded_sparql_query'}:
        raise ProvenanceAuditError('Invalid benchmark measurement keys')
    for measurement in samples.values():
        if not isinstance(measurement, dict) or set(measurement) != {'samples_ns','median_ns','min_ns','max_ns'}:
            raise ProvenanceAuditError('Invalid benchmark measurement shape')
        values = measurement['samples_ns']
        if not isinstance(values, list) or len(values) != repetitions or any(
            type(value) is not int or value < 0 or value > MAX_TIMINGS_NS for value in values):
            raise ProvenanceAuditError('Invalid timing samples')
        if (measurement['median_ns'] != median(values) or
                measurement['min_ns'] != min(values) or
                measurement['max_ns'] != max(values)):
            raise ProvenanceAuditError('Timing statistics do not match samples')


def verify_report(directory: Path, repository: Path, *, mode: str,
                  knowledge_graph: str | None, query_id: str, argument: str,
                  limit: int = 100, repeats: int = 3) -> dict:
    root = Path(directory).resolve(strict=True)
    source = Path(repository).resolve(strict=True)
    if root == source or source in root.parents:
        raise ProvenanceAuditError('Detached report must be outside repository')
    raw = ri01._read(root / 'ri03-scientific-dataset.nq', ri01.MAX_BYTES)
    content = ri01._read(root / 'ri03-audit-report.json', ri01.MAX_REPORT_BYTES)
    try:
        report = json.loads(content)
    except (ValueError, UnicodeError) as exc:
        raise ProvenanceAuditError('Invalid detached JSON report') from exc
    if type(report) is not dict or report.get('schema_version') != SCHEMA:
        raise ProvenanceAuditError('Unknown RI-03 report schema')
    digest = report.get('report_sha256')
    if type(digest) is not str or len(digest) != 64 or _digest(canonical({
        k:v for k,v in report.items() if k != 'report_sha256'})) != digest:
        raise ProvenanceAuditError('Detached report digest mismatch')
    if content != canonical(report):
        raise ProvenanceAuditError('Detached report bytes are not canonical')
    if not isinstance(report.get('benchmark'), dict) or report['benchmark'].get('repeats') != repeats:
        raise ProvenanceAuditError('Benchmark repetition settings changed')
    _timing_shape(report['benchmark'])
    view, state = ri01.resolve_view(source, mode=mode, knowledge_graph=knowledge_graph)
    index = ri02.build_scientific_index(view, store_state=state)
    expected = _report_core(index, mode=mode, query_id=query_id, argument=argument, limit=limit)
    actual = {k:v for k,v in report.items() if k not in ('benchmark','report_sha256')}
    if actual != expected or raw != index.nquads:
        raise ProvenanceAuditError('Detached RI-03 artifact differs from verified source replay')
    # A second RDFLib parsing verifies N-Quad syntax/context membership.
    from rdflib import Dataset
    ds = Dataset(default_union=False)
    try:
        ds.parse(data=raw.decode('utf-8'), format='nquads')
    except Exception as exc:
        raise ProvenanceAuditError('Detached N-Quads are invalid') from exc
    if set(ds.quads((None,None,None,None))) != set(index.dataset.quads((None,None,None,None))):
        raise ProvenanceAuditError('Reparsed RDF terms do not match verified graph')
    return report


def write_report(directory: Path, repository: Path, report: dict, nquads: bytes):
    target = ri01._safe_output(directory, repository)
    target.mkdir(mode=0o700)
    ri01._new_file(target / 'ri03-scientific-dataset.nq', nquads)
    ri01._new_file(target / 'ri03-audit-report.json', canonical(report))


def main(argv=None):
    parser = argparse.ArgumentParser(description='RI-03 verified RDF provenance and performance assessment')
    parser.add_argument('--repository', required=True)
    parser.add_argument('--mode', choices=('persisted','candidate'), default='persisted')
    parser.add_argument('--knowledge-graph')
    parser.add_argument('--query', choices=QUERIES, default='concept_evidence_paths')
    parser.add_argument('--argument', required=True)
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args(argv)
    kwargs = dict(mode=args.mode, knowledge_graph=args.knowledge_graph, query_id=args.query,
                  argument=args.argument, limit=args.limit, repeats=args.repeats)
    if args.verify:
        report = verify_report(Path(args.output_dir), Path(args.repository), **kwargs)
    else:
        report, raw = build_report(Path(args.repository), **kwargs)
        write_report(Path(args.output_dir), Path(args.repository), report, raw)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, TypeError, OSError, KeyError) as exc:
        import sys
        print('RI-03 rejected:', exc, file=sys.stderr)
        raise SystemExit(2)
