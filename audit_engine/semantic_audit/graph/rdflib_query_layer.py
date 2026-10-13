"""RI-01: detached, source-verified RDFLib datasets and bounded SPARQL catalog.

G4 canonical serialization and GE state remain authoritative. This adapter uses
RDFLib for in-memory RDF terms, named graphs and fixed, read-only SPARQL queries.
It never evaluates caller-supplied SPARQL and never mutates a scientific source.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from typing import Any
from urllib.parse import quote

from rdflib import Dataset, Graph, Literal, URIRef
from rdflib.namespace import RDF, XSD

from audit_engine.semantic_audit.graph.domain_integration import (
    GraphDomainView, from_scientific_graph,
)
from audit_engine.semantic_audit.graph.persistent_domain_state import (
    PersistentDomainGraphStore, canonical, _input_path,
)

SCHEMA = 'ri01-rdflib-query-view/v1'
MAX_QUERY_LIMIT = 200
MAX_QUADS = 350_000
MAX_BYTES = 60_000_000
MAX_REPORT_BYTES = 120_000
# Only explicit, scientifically useful fields are projected. All other metadata
# remains in the G4 JSON literals. Never infer claims from opaque metadata.
FIELDS = frozenset({
    'name', 'statement', 'status', 'framework', 'type', 'source_id_unverified',
    'claimed_relation_type', 'status_unverified',
})
FIELD_RE = re.compile(r'^[a-z_]{1,64}$')


class RDFQueryLayerError(ValueError):
    """Unsafe input, inconsistent provenance, or unverifiable detached RDF view."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _uri(kind: str, ident: str) -> URIRef:
    from audit_engine.semantic_audit.graph.rdf_export import NS
    if not isinstance(ident, str) or not ident or len(ident) > 4096:
        raise RDFQueryLayerError('Invalid resource identifier')
    return URIRef(NS + quote(f'{kind}:{ident}', safe=''))


def _field_iri(field: str) -> URIRef:
    if field not in FIELDS:
        raise RDFQueryLayerError('Field is not in the explicit RDF query vocabulary')
    return _uri('query-field', field)


def _literal(value: Any) -> Literal | None:
    if isinstance(value, str):
        return Literal(value, datatype=XSD.string)
    if type(value) is bool:
        return Literal(value, datatype=XSD.boolean)
    if type(value) is int:
        return Literal(value, datatype=XSD.integer)
    if type(value) is float and math.isfinite(value):
        return Literal(value, datatype=XSD.double)
    # Structured, null or non-finite values have no simple typed projection.
    return None


def _nq(ds: Dataset, contexts: tuple[URIRef, ...]) -> bytes:
    """Canonical, BNode-free N-Quads built from RDFLib term serialization."""
    lines = set()
    for context_iri in contexts:
        context = ds.graph(context_iri)
        for s, p, o in context:
            if (not isinstance(s, URIRef) or not isinstance(p, URIRef)
                    or not isinstance(o, (URIRef, Literal))):
                raise RDFQueryLayerError('Blank nodes are forbidden in the detached dataset')
            lines.add(f'{s.n3()} {p.n3()} {o.n3()} {context_iri.n3()} .\n')
            if len(lines) > MAX_QUADS:
                raise RDFQueryLayerError('Dataset exceeds quad limit')
    raw = ''.join(sorted(lines)).encode('utf-8')
    if len(raw) > MAX_BYTES:
        raise RDFQueryLayerError('Dataset exceeds byte limit')
    return raw


@dataclass
class VerifiedRDFView:
    """A derived, non-authoritative in-memory view, never a writable source."""
    dataset: Dataset
    asserted_context: URIRef
    fields_context: URIRef
    provenance_context: URIRef
    source_view: GraphDomainView
    g4_manifest: dict
    provenance: dict
    nquads: bytes

    def query(self, query_id: str, argument: str, limit: int = 100) -> list[dict]:
        """Execute one of three *fixed* parameterized SELECT queries only."""
        if type(limit) is not int or not 1 <= limit <= MAX_QUERY_LIMIT:
            raise RDFQueryLayerError('Query limit must be an integer from 1 to 200')
        if not isinstance(argument, str) or not argument or len(argument) > 4096:
            raise RDFQueryLayerError('Invalid query argument')
        q = self.asserted_context.n3()
        f = self.fields_context.n3()
        contains_node = _uri('property', 'containsNode').n3()
        contains_edge = _uri('property', 'containsEdge').n3()
        node_id = _uri('property', 'nodeIdentifier').n3()
        node_type = _uri('property', 'entityType').n3()
        rel_type = _uri('property', 'relationType').n3()
        occurrence = _uri('property', 'parallelEdgeOccurrence').n3()
        snap = _uri('snapshot', self.source_view.fingerprint).n3()
        bindings = {}
        if query_id == 'nodes_by_type':
            bindings['wanted'] = Literal(argument, datatype=XSD.string)
            sparql = f'''SELECT ?node ?nodeId ?entityType WHERE {{
              GRAPH {q} {{ {snap} {contains_node} ?node .
                ?node {node_id} ?nodeId ; {node_type} ?entityType .
                FILTER(?entityType = ?wanted) }}
              }} ORDER BY ?nodeId LIMIT {limit}'''
        elif query_id == 'edge_occurrences_by_relation':
            bindings['wanted'] = Literal(argument, datatype=XSD.string)
            sparql = f'''SELECT ?statement ?source ?target ?relation ?occurrence WHERE {{
              GRAPH {q} {{ {snap} {contains_edge} ?statement .
                ?statement {RDF.subject.n3()} ?source ; {RDF.object.n3()} ?target ;
                  {rel_type} ?relation ; {occurrence} ?occurrence .
                FILTER(?relation = ?wanted) }}
              }} ORDER BY ?statement LIMIT {limit}'''
        elif query_id == 'nodes_by_field':
            if argument not in FIELDS:
                raise RDFQueryLayerError('Unknown field for SPARQL catalog')
            prop = _field_iri(argument).n3()
            sparql = f'''SELECT ?node ?value WHERE {{
                GRAPH {q} {{ {snap} {contains_node} ?node }}
                GRAPH {f} {{ ?node {prop} ?value }}
              }} ORDER BY ?node ?value LIMIT {limit}'''
        else:
            raise RDFQueryLayerError('Unknown catalog query; arbitrary SPARQL is prohibited')
        try:
            response = self.dataset.query(sparql, initBindings=bindings)
        except Exception as exc:
            raise RDFQueryLayerError('Fixed RDFLib SPARQL execution failed') from exc
        answer: list[dict] = []
        for row in response:
            if len(answer) >= limit:
                raise RDFQueryLayerError('SPARQL query escaped row limit')
            answer.append({str(name): _term(value) for name, value in row.asdict().items()})
        return answer


def _term(value: Any) -> dict:
    if isinstance(value, URIRef):
        return {'type': 'iri', 'value': str(value)}
    if isinstance(value, Literal):
        return {'type': 'literal', 'value': str(value),
                'datatype': str(value.datatype) if value.datatype is not None else None,
                'language': value.language}
    raise RDFQueryLayerError('Unexpected RDF term in query result')


def build_verified_dataset(view: GraphDomainView, *, store_state: dict | None = None) -> VerifiedRDFView:
    """Verify G4 export then derive named graphs without changing canonical bytes."""
    from audit_engine.semantic_audit.graph.rdf_export import export_view
    from audit_engine.semantic_audit.graph.rdf_interoperability import (
        verify_rdf_interoperability, _read_rdf,
    )
    bundle = export_view(view, store_state=store_state)
    verified = verify_rdf_interoperability(view, bundle, store_state=store_state)
    source = _read_rdf(bundle)
    source_snapshot = view.snapshot()
    context_suffix = source_snapshot['snapshot_sha256']
    asserted_iri = _uri('rdf-context', f'{context_suffix}:asserted')
    fields_iri = _uri('rdf-context', f'{context_suffix}:fields')
    provenance_iri = _uri('rdf-context', f'{context_suffix}:provenance')
    dataset = Dataset(default_union=False)
    asserted = dataset.graph(asserted_iri)
    for triple in source:
        asserted.add(triple)
    if set(asserted) != set(source) or len(asserted) != verified['triple_count']:
        raise RDFQueryLayerError('G4 RDF triple set mismatch')

    fields = dataset.graph(fields_iri)
    for node in view.graph.nodes:
        resource = _uri('node', node.node_id)
        for key, value in node.attributes.items():
            if key in FIELDS:
                lit = _literal(value)
                if lit is not None:
                    fields.add((resource, _field_iri(key), lit))
    # Edge attributes remain exclusively in the reified G4 representation:
    # this avoids collapsing parallel occurrences into duplicate triples.

    provenance = dataset.graph(provenance_iri)
    resource = _uri('query-view', context_suffix)
    prov = {
        'source_graph_fingerprint': view.fingerprint,
        'source_snapshot_sha256': context_suffix,
        'source_input_sha256': view.input_sha256,
        'g4_manifest_sha256': bundle['manifest']['manifest_sha256'],
        'persisted_store_head': store_state['head'] if store_state else None,
        'persisted_store_generation': store_state['generation'] if store_state else None,
    }
    for key, value in prov.items():
        if value is not None:
            lit = _literal(value)
            if lit is None:
                raise RDFQueryLayerError('Invalid source provenance value')
            provenance.add((resource, _uri('query-provenance', key), lit))
    for key, context in (('asserted_context', asserted_iri),
                         ('fields_context', fields_iri), ('provenance_context', provenance_iri)):
        provenance.add((resource, _uri('query-provenance', key), context))
    for key in ('scientific_truth_established', 'semantic_entailment_verified',
                'automatic_approval_permitted', 'authoritative_mutation_permitted'):
        provenance.add((resource, _uri('query-provenance', key), Literal(False, datatype=XSD.boolean)))
    contexts = (asserted_iri, fields_iri, provenance_iri)
    nquads = _nq(dataset, contexts)
    return VerifiedRDFView(dataset, *contexts, view, bundle['manifest'], prov, nquads)


def resolve_view(repository: Path, *, mode: str = 'persisted',
                 knowledge_graph: str | None = None) -> tuple[GraphDomainView, dict | None]:
    root = Path(repository).resolve(strict=True)
    if mode == 'persisted':
        store = PersistentDomainGraphStore(root / '.graph-state/scientific')
        state = store.verify()
        if state.get('status') != 'verified':
            raise RDFQueryLayerError('Persisted GE-02 state is not verified')
        view = store.current_view()
        if view is None:
            raise RDFQueryLayerError('Persisted graph has no source view')
        return view, state
    if mode == 'candidate':
        if not knowledge_graph:
            raise RDFQueryLayerError('Candidate mode requires a knowledge graph path')
        from audit_engine.semantic_audit.graph.domain_integration import _read_json
        return from_scientific_graph(_read_json(_input_path(root, knowledge_graph))), None
    raise RDFQueryLayerError('Mode must be persisted or candidate')


def build_report(repository: Path, *, mode: str, knowledge_graph: str | None,
                 query_id: str, argument: str, limit: int = 100) -> tuple[dict, bytes]:
    view, state = resolve_view(repository, mode=mode, knowledge_graph=knowledge_graph)
    derived = build_verified_dataset(view, store_state=state)
    results = derived.query(query_id, argument, limit)
    report = {
        'schema_version': SCHEMA,
        'mode': mode,
        'query_id': query_id,
        'query_argument': argument,
        'query_limit': limit,
        'results': results,
        'result_count': len(results),
        'contexts': [str(c) for c in (derived.asserted_context,
                                      derived.fields_context, derived.provenance_context)],
        'dataset_quad_count': sum(1 for _ in derived.dataset.quads((None,None,None,None))),
        'dataset_nquads_sha256': _sha(derived.nquads),
        **derived.provenance,
        'g4_source_triples_preserved': True,
        'parallel_edge_occurrences_preserved': True,
        'arbitrary_sparql_permitted': False,
        'scientific_truth_established': False,
        'semantic_entailment_verified': False,
        'automatic_approval_permitted': False,
        'authoritative_mutation_permitted': False,
    }
    report['report_sha256'] = _sha(canonical(report))
    if len(canonical(report)) > MAX_REPORT_BYTES:
        raise RDFQueryLayerError('Query report exceeds resource limit')
    return report, derived.nquads


def _new_file(path: Path, raw: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())


def _safe_output(output: Path, repository: Path) -> Path:
    target = Path(output).absolute()
    repo = Path(repository).resolve(strict=True)
    if target == repo or repo in target.parents or target.is_symlink() or target.exists():
        raise RDFQueryLayerError('Output must be a new directory outside source repository')
    if not target.parent.is_dir() or any(p.is_symlink() for p in target.parents):
        raise RDFQueryLayerError('Unsafe output parent')
    return target


def write_report(output: Path, repository: Path, report: dict, nquads: bytes) -> None:
    directory = _safe_output(output, repository)
    directory.mkdir(mode=0o700)
    _new_file(directory / 'rdf-dataset.nq', nquads)
    _new_file(directory / 'rdf-query-report.json', canonical(report))


def _read(path: Path, limit: int) -> bytes:
    if path.is_symlink():
        raise RDFQueryLayerError('Symlinked output forbidden')
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os,'O_NONBLOCK',0))
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > limit:
            raise RDFQueryLayerError('Invalid detached artifact file')
        raw = os.read(fd, limit + 1)
        if len(raw) != st.st_size:
            raise RDFQueryLayerError('Artifact changed while reading')
        return raw
    finally:
        os.close(fd)


def verify_report(output: Path, repository: Path, *, mode: str, knowledge_graph: str | None,
                  query_id: str, argument: str, limit: int) -> dict:
    directory = Path(output).resolve(strict=True)
    repo = Path(repository).resolve(strict=True)
    if directory == repo or repo in directory.parents:
        raise RDFQueryLayerError('Detached artifact cannot be inside source repository')
    report, nquads = build_report(repo, mode=mode, knowledge_graph=knowledge_graph,
                                 query_id=query_id, argument=argument, limit=limit)
    found_nq = _read(directory / 'rdf-dataset.nq', MAX_BYTES)
    found_report = _read(directory / 'rdf-query-report.json', MAX_REPORT_BYTES)
    if found_nq != nquads or found_report != canonical(report):
        raise RDFQueryLayerError('Detached RDF/query artifact differs from verified source replay')
    # RDFLib independent parser checks the serialization's quad semantics.
    parsed = Dataset(default_union=False)
    try:
        parsed.parse(data=found_nq.decode('utf-8'), format='nquads')
    except Exception as exc:
        raise RDFQueryLayerError('Detached N-Quads cannot be parsed') from exc
    if len(list(parsed.quads((None,None,None,None)))) != report['dataset_quad_count']:
        raise RDFQueryLayerError('Detached quad count mismatch')
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='RI-01 verified RDFLib named-graph SPARQL catalog')
    parser.add_argument('--repository', required=True)
    parser.add_argument('--mode', choices=('persisted','candidate'), default='persisted')
    parser.add_argument('--knowledge-graph')
    parser.add_argument('--query', required=True,
                        choices=('nodes_by_type','edge_occurrences_by_relation','nodes_by_field'))
    parser.add_argument('--argument', required=True)
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args(argv)
    kwargs = dict(mode=args.mode, knowledge_graph=args.knowledge_graph, query_id=args.query,
                  argument=args.argument, limit=args.limit)
    if args.verify:
        report = verify_report(Path(args.output_dir), Path(args.repository), **kwargs)
    else:
        report, nquads = build_report(Path(args.repository), **kwargs)
        write_report(Path(args.output_dir), Path(args.repository), report, nquads)
    print(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (RDFQueryLayerError, ValueError, TypeError, OSError, KeyError) as exc:
        print('RI-01 RDFLib query rejected:', exc, file=__import__('sys').stderr)
        raise SystemExit(2)
