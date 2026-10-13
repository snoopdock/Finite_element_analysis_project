"""RI-02: Verified RDFLib scientific index, vocabulary and fixed SPARQL queries.

Non-authoritative. The original G4 output, RI-01 dataset and GE-02 graph history
are left unchanged. The G4.6 structural verifier must succeed *before* this
module indexes any node or edge. No remote RDF loading or arbitrary SPARQL.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from rdflib import Dataset, Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from audit_engine.semantic_audit.graph import rdflib_query_layer as ri01
from audit_engine.semantic_audit.graph.persistent_domain_state import canonical

SCHEMA = 'ri02-verified-scientific-index/v1'
MAX_LITERAL = 8192
MAX_RESULTS = ri01.MAX_QUERY_LIMIT
MAX_INDEX_TRIPLES = 150_000

# Deliberately closed and documented scalar vocabulary. A field is indexed only
# on the correct resource kind. None of these imply a verified scientific fact.
# (kind, source field): (public predicate, expected Python type)
NODE_ATTRIBUTES = {
    'name': ('conceptName', str),
    'statement': ('propositionStatement', str),
    'status': ('reviewStatusUnverified', str),
    'framework': ('frameworkName', str),
    'type': ('sourceDeclaredType', str),
    'source_id_unverified': ('sourceIdentifierUnverified', str),
}
NODE_METADATA = {'original_id': ('originalUUID', str)}
EDGE_ATTRIBUTES = {
    'claimed_relation_type': ('claimedRelationTypeUnverified', str),
    'status_unverified': ('relationStatusUnverified', str),
    'weight': ('edgeWeight', (int, float)),
}
EDGE_METADATA = {
    'relationship_id': ('originalRelationshipUUID', str),
    'source_verified': ('edgeSourceVerifiedFlag', bool),
    'scientific_support_verified': ('scientificSupportVerifiedFlag', bool),
    'semantic_entailment_verified': ('semanticEntailmentVerifiedFlag', bool),
}


class ScientificIndexError(ri01.RDFQueryLayerError):
    """Structural mismatch, unsafe projection, or invalid detached index."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _property(name: str) -> URIRef:
    return ri01._uri('property', name)


def _indexed(name: str) -> URIRef:
    return ri01._uri('scientific-index', name)


def _only(g, subject, predicate):
    values = list(g.objects(subject, predicate))
    if len(values) != 1:
        raise ScientificIndexError('G4 statement is missing or ambiguously encoded')
    return values[0]


def _g4_text(g, subject, name: str) -> str:
    term = _only(g, subject, _property(name))
    if not isinstance(term, Literal) or term.language is not None or term.datatype not in (None, XSD.string):
        raise ScientificIndexError('Incorrect G4 literal datatype')
    return str(term)


def _g4_dict(g, subject, name: str) -> dict:
    content = _g4_text(g, subject, name)
    if len(content) > ri01.MAX_BYTES:
        raise ScientificIndexError('Oversized G4 JSON field')
    try:
        data = json.loads(content)
    except (ValueError, UnicodeError) as exc:
        raise ScientificIndexError('Unparseable G4 JSON field') from exc
    if not isinstance(data, dict):
        raise ScientificIndexError('G4 edge metadata must be a JSON object')
    return data


def _edge_key(src, dst, relation, attrs, meta) -> tuple:
    return (str(src), str(dst), relation, canonical(attrs), canonical(meta))


def _verified_statements(view, asserted):
    """Join EACH semantic edge to an independently G4-verified statement.

    No reliance on edge iteration order or text labels; identical parallel
    relationships consume distinct G4 statement resources.
    """
    snapshot = ri01._uri('snapshot', view.fingerprint)
    contains = _property('containsEdge')
    sources = list(asserted.objects(snapshot, contains))
    if len(sources) != len(set(sources)):
        raise ScientificIndexError('Repeated G4 statement identity')
    g4 = {}
    for statement in sources:
        if not isinstance(statement, URIRef):
            raise ScientificIndexError('Unexpected G4 statement term')
        if _only(asserted, statement, RDF.type) != RDF.Statement:
            raise ScientificIndexError('G4 edge occurrence is not an RDF Statement')
        src = _only(asserted, statement, RDF.subject)
        dst = _only(asserted, statement, RDF.object)
        rel = _g4_text(asserted, statement, 'relationType')
        attrs = _g4_dict(asserted, statement, 'attributesJson')
        meta = _g4_dict(asserted, statement, 'metadataJson')
        ordinal = _only(asserted, statement, _property('parallelEdgeOccurrence'))
        if (not isinstance(src, URIRef) or not isinstance(dst, URIRef)
                or not isinstance(ordinal, Literal) or ordinal.datatype != XSD.nonNegativeInteger):
            raise ScientificIndexError('Malformed G4 reified edge')
        key = _edge_key(src, dst, rel, attrs, meta)
        g4.setdefault(key, []).append(statement)
    source_expected = Counter(
        _edge_key(ri01._uri('node', edge.source_id), ri01._uri('node', edge.target_id),
                  edge.relation_type, edge.attributes, edge.metadata)
        for edge in view.graph.edges
    )
    actual = Counter({key: len(statements) for key, statements in g4.items()})
    if actual != source_expected:
        raise ScientificIndexError('G4 edge occurrences do not match verified graph source')
    return sorted((statement, key) for key, statements in g4.items() for statement in statements)


def _typed(value: Any, expected: type | tuple[type, ...]) -> Literal:
    if expected == str:
        if not isinstance(value, str) or len(value) > MAX_LITERAL:
            raise ScientificIndexError('Invalid indexed string')
        return Literal(value, datatype=XSD.string)
    if expected == bool:
        if type(value) is not bool:
            raise ScientificIndexError('Invalid indexed boolean')
        return Literal(value, datatype=XSD.boolean)
    if expected == (int, float):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ScientificIndexError('Invalid numeric edge weight')
        return Literal(value, datatype=XSD.integer if type(value) is int else XSD.double)
    raise ScientificIndexError('Unexpected vocabulary declaration')


def _project_fields(index, resource, payload, spec):
    for key, (predicate, expected) in spec.items():
        if key in payload:
            index.add((resource, _indexed(predicate), _typed(payload[key], expected)))


def _vocabulary(vocab):
    combined = [*NODE_ATTRIBUTES.values(), *NODE_METADATA.values(),
                *EDGE_ATTRIBUTES.values(), *EDGE_METADATA.values()]
    for predicate, expected in combined:
        prop = _indexed(predicate)
        vocab.add((prop, RDF.type, RDF.Property))
        vocab.add((prop, RDFS.label, Literal(predicate, datatype=XSD.string)))
        datatypes = ((XSD.string,) if expected == str else
                     (XSD.boolean,) if expected == bool else
                     (XSD.integer, XSD.double))
        for datatype in datatypes:
            vocab.add((prop, _indexed('declaredScalarDatatype'), datatype))
    # This declaration documents projection vocabulary; it is NOT an OWL
    # entailment claim, SHACL validation result, or verified scientific status.
    vocab.add((ri01._uri('ri02-vocabulary', SCHEMA), _indexed('doesNotEstablishTruth'),
               Literal(True, datatype=XSD.boolean)))


@dataclass
class ScientificIndex:
    dataset: Dataset
    contexts: tuple[URIRef, ...]
    base: ri01.VerifiedRDFView
    nquads: bytes
    projection_counts: dict

    def query(self, query_id: str, argument: str, limit: int = 100) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= MAX_RESULTS:
            raise ScientificIndexError('Query limit must be an integer between 1 and 200')
        if not isinstance(argument, str) or not argument or len(argument) > 4096:
            raise ScientificIndexError('Unsafe query argument')
        a, idx = self.base.asserted_context.n3(), self.contexts[3].n3()
        snap = ri01._uri('snapshot', self.base.source_view.fingerprint).n3()
        contains_node = _property('containsNode').n3()
        contains_edge = _property('containsEdge').n3()
        typ = _property('entityType').n3()
        relation = _property('relationType').n3()
        occurrence = _property('parallelEdgeOccurrence').n3()
        wanted = None
        if query_id == 'concepts_by_status':
            wanted = Literal(argument, datatype=XSD.string)
            q = f'''SELECT ?node ?name ?status WHERE {{
              GRAPH {a} {{ {snap} {contains_node} ?node . ?node {typ} "ScientificConcept" . }}
              GRAPH {idx} {{ ?node {_indexed('reviewStatusUnverified').n3()} ?status .
                              OPTIONAL {{ ?node {_indexed('conceptName').n3()} ?name . }} }}
              FILTER(?status = ?wanted)
            }} ORDER BY ?node ?name LIMIT {limit}'''
        elif query_id in ('propositions_for_concept', 'citations_for_entity', 'subconcepts_of'):
            entity = ri01._uri('node', argument)
            wanted = entity
            relationship = {'propositions_for_concept':'HAS_CONCEPT',
                            'citations_for_entity':'CITES_SOURCE',
                            'subconcepts_of':'SUBCONCEPT_OF'}[query_id]
            if query_id == 'subconcepts_of':
                bound = '?target = ?wanted'
            elif query_id == 'propositions_for_concept':
                bound = '?target = ?wanted'
            else:
                bound = '?source = ?wanted'
            q = f'''SELECT ?statement ?source ?target ?ordinal WHERE {{
              GRAPH {a} {{ {snap} {contains_edge} ?statement .
                ?statement {RDF.subject.n3()} ?source ; {RDF.object.n3()} ?target ;
                  {relation} "{relationship}" ; {occurrence} ?ordinal . }}
              FILTER({bound})
            }} ORDER BY ?statement LIMIT {limit}'''
        elif query_id == 'relations_for_entity':
            wanted = ri01._uri('node', argument)
            q = f'''SELECT ?statement ?target ?relation ?ordinal WHERE {{
              GRAPH {a} {{ {snap} {contains_edge} ?statement .
                ?statement {RDF.subject.n3()} ?wanted ; {RDF.object.n3()} ?target ;
                  {relation} ?relation ; {occurrence} ?ordinal . }}
            }} ORDER BY ?statement LIMIT {limit}'''
        elif query_id == 'edges_by_claimed_type':
            wanted = Literal(argument, datatype=XSD.string)
            q = f'''SELECT ?statement ?source ?target ?ordinal ?claimed WHERE {{
              GRAPH {a} {{ {snap} {contains_edge} ?statement .
                ?statement {RDF.subject.n3()} ?source ; {RDF.object.n3()} ?target ;
                  {occurrence} ?ordinal . }}
              GRAPH {idx} {{ ?statement {_indexed('claimedRelationTypeUnverified').n3()} ?claimed . }}
              FILTER(?claimed = ?wanted)
            }} ORDER BY ?statement LIMIT {limit}'''
        elif query_id == 'nodes_by_indexed_field':
            # A field name is selected from a fixed vocabulary, never used as
            # untrusted SPARQL text or a property path.
            allowed = {name: pred for name,(pred,_) in NODE_ATTRIBUTES.items()}
            if argument not in allowed:
                raise ScientificIndexError('Unknown or non-node index field')
            prop = _indexed(allowed[argument]).n3()
            q = f'''SELECT ?node ?value WHERE {{
              GRAPH {a} {{ {snap} {contains_node} ?node . }}
              GRAPH {idx} {{ ?node {prop} ?value . }}
            }} ORDER BY ?node ?value LIMIT {limit}'''
        else:
            raise ScientificIndexError('Only predefined, bounded read-only SPARQL queries are allowed')
        try:
            result = self.dataset.query(q, initBindings=({'wanted': wanted} if wanted is not None else {}))
        except Exception as exc:
            raise ScientificIndexError('Fixed RDFLib SPARQL query failed') from exc
        rows = []
        for row in result:
            if len(rows) >= limit:
                raise ScientificIndexError('Query exceeded bounded result limit')
            rows.append({str(k): ri01._term(v) for k,v in row.asdict().items()})
        return rows


def build_scientific_index(view, *, store_state: dict | None = None) -> ScientificIndex:
    """Construct a *derived* RDF view following independent G4/G4.6 checking."""
    base = ri01.build_verified_dataset(view, store_state=store_state)
    source = base.dataset.graph(base.asserted_context)
    verified = _verified_statements(view, source)
    idx_uri = ri01._uri('rdf-context', f'{view.snapshot()["snapshot_sha256"]}:scientific-index-v1')
    vocab_uri = ri01._uri('rdf-context', f'{view.snapshot()["snapshot_sha256"]}:index-vocabulary-v1')
    contexts = (base.asserted_context, base.fields_context, base.provenance_context,
                idx_uri, vocab_uri)
    ds = Dataset(default_union=False)
    for s,p,o,g in base.dataset.quads((None,None,None,None)):
        ds.graph(g.identifier if hasattr(g,'identifier') else g).add((s,p,o))
    index = ds.graph(idx_uri)
    for node in view.graph.nodes:
        resource = ri01._uri('node', node.node_id)
        if (resource, None, None) not in source and (None,None,resource) not in source:
            raise ScientificIndexError('Node absent from independently verified G4 RDF')
        _project_fields(index, resource, node.attributes, NODE_ATTRIBUTES)
        _project_fields(index, resource, node.metadata, NODE_METADATA)
    for statement, key in verified:
        source_id, target_id, relation, raw_attrs, raw_meta = key
        _project_fields(index, statement, json.loads(raw_attrs), EDGE_ATTRIBUTES)
        _project_fields(index, statement, json.loads(raw_meta), EDGE_METADATA)
    _vocabulary(ds.graph(vocab_uri))
    if len(index) > MAX_INDEX_TRIPLES:
        raise ScientificIndexError('Scientific index resource limit exceeded')
    nquads = ri01._nq(ds, contexts)
    return ScientificIndex(ds, contexts, base, nquads, {
        'source_node_count': len(view.graph.nodes),
        'source_edge_occurrence_count': len(view.graph.edges),
        'indexed_scalar_triple_count': len(index),
        'vocabulary_triple_count': len(ds.graph(vocab_uri)),
        'asserted_g4_triple_count': len(ds.graph(base.asserted_context)),
    })


def build_report(repository: Path, *, mode: str, knowledge_graph: str | None,
                 query_id: str, argument: str, limit: int = 100):
    view, state = ri01.resolve_view(repository, mode=mode, knowledge_graph=knowledge_graph)
    enriched = build_scientific_index(view, store_state=state)
    results = enriched.query(query_id, argument, limit)
    report = {
        'schema_version': SCHEMA, 'mode': mode, 'query_id': query_id,
        'query_argument': argument, 'query_limit': limit, 'results': results,
        'result_count': len(results),
        'contexts': [str(x) for x in enriched.contexts],
        'dataset_quad_count': sum(len(enriched.dataset.graph(g)) for g in enriched.contexts),
        'dataset_nquads_sha256': _sha(enriched.nquads),
        'ri01_dataset_sha256': _sha(enriched.base.nquads),
        'g4_manifest_sha256': enriched.base.g4_manifest['manifest_sha256'],
        **enriched.base.provenance, **enriched.projection_counts,
        'g4_source_triples_preserved': True,
        'parallel_edge_occurrences_preserved': True,
        'arbitrary_sparql_permitted': False,
        'automatic_approval_permitted': False,
        'authoritative_mutation_permitted': False,
        'scientific_truth_established': False,
        'semantic_entailment_verified': False,
    }
    report['report_sha256'] = _sha(canonical(report))
    if len(canonical(report)) > ri01.MAX_REPORT_BYTES:
        raise ScientificIndexError('Detached scientific index report exceeds byte limit')
    return report, enriched.nquads


def write_report(output: Path, repository: Path, report: dict, nquads: bytes) -> None:
    folder = ri01._safe_output(output, repository)
    folder.mkdir(mode=0o700)
    ri01._new_file(folder / 'scientific-index.nq', nquads)
    ri01._new_file(folder / 'scientific-index-report.json', canonical(report))


def verify_report(output: Path, repository: Path, *, mode: str,
                  knowledge_graph: str | None, query_id: str, argument: str,
                  limit: int = 100) -> dict:
    root = Path(output).resolve(strict=True)
    source = Path(repository).resolve(strict=True)
    if source == root or source in root.parents:
        raise ScientificIndexError('Detached output cannot be inside the repository')
    report, nquads = build_report(source, mode=mode, knowledge_graph=knowledge_graph,
                                 query_id=query_id, argument=argument, limit=limit)
    nq_bytes = ri01._read(root / 'scientific-index.nq', ri01.MAX_BYTES)
    report_bytes = ri01._read(root / 'scientific-index-report.json', ri01.MAX_REPORT_BYTES)
    if nq_bytes != nquads or report_bytes != canonical(report):
        raise ScientificIndexError('Detached report differs from independently verified source replay')
    reparsed = Dataset(default_union=False)
    try:
        reparsed.parse(data=nq_bytes.decode('utf-8'), format='nquads')
    except Exception as exc:
        raise ScientificIndexError('Detached N-Quads are invalid') from exc
    if len(set(reparsed.quads((None,None,None,None)))) != report['dataset_quad_count']:
        raise ScientificIndexError('Detached RDF quad count mismatch')
    if {str(g) for _,_,_,g in reparsed.quads((None,None,None,None))} != set(report['contexts']):
        raise ScientificIndexError('Detached named graph contexts mismatch')
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description='RI-02 verified, read-only scientific RDFLib index')
    p.add_argument('--repository', required=True)
    p.add_argument('--mode', choices=('persisted','candidate'), default='persisted')
    p.add_argument('--knowledge-graph')
    p.add_argument('--query', required=True, choices=(
        'concepts_by_status','propositions_for_concept','citations_for_entity',
        'subconcepts_of','relations_for_entity','edges_by_claimed_type',
        'nodes_by_indexed_field'))
    p.add_argument('--argument', required=True)
    p.add_argument('--limit', type=int, default=100)
    p.add_argument('--output-dir', required=True)
    p.add_argument('--verify', action='store_true')
    args = p.parse_args(argv)
    options = dict(mode=args.mode, knowledge_graph=args.knowledge_graph,
                   query_id=args.query, argument=args.argument, limit=args.limit)
    if args.verify:
        result = verify_report(Path(args.output_dir), Path(args.repository), **options)
    else:
        result, nq = build_report(Path(args.repository), **options)
        write_report(Path(args.output_dir), Path(args.repository), result, nq)
    print(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print('RI-02 rejected:', exc, file=__import__('sys').stderr)
        raise SystemExit(2)
