"""G4.6: source-bound, read-only RDF interoperability and structural round-trip audit.

This module never imports RDF into an authoritative graph. It interprets the
project's published RDF v1 vocabulary *as data*, independently parses both RDF
serializations using RDFLib, reconstructs attributed multigraph occurrences,
and compares them with a verified GE graph snapshot. A successful check proves
bounded structural equivalence, not scientific truth or semantic entailment.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF as RDF_NS, XSD as XSD_NS

from audit_engine.semantic_audit.graph.domain_integration import GraphDomainError, from_scientific_graph
from audit_engine.semantic_audit.graph.persistent_domain_state import (
    GraphStoreError, PersistentDomainGraphStore, canonical, parse, _input_path,
)
from audit_engine.semantic_audit.graph.rdf_export import (
    RDFExportError, NS, MAX_TRIPLES, read_export, export_view, _new_file,
)

SCHEMA = 'g4-rdf-interoperability/v1'
REPORT_MAX_BYTES = 32_768


class RDFInteroperabilityError(ValueError):
    """The RDF bundle cannot safely be identified with the verified source."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _uri(kind: str, value: str) -> URIRef:
    return URIRef(NS + quote(kind + ':' + value, safe=''))


def _property(name: str) -> URIRef:
    return _uri('property', name)


def _only(graph: Graph, subject: URIRef, predicate: URIRef):
    values = list(graph.objects(subject, predicate))
    if len(values) != 1:
        raise RDFInteroperabilityError(f'Expected exactly one value for {predicate}')
    return values[0]


def _text(graph: Graph, subject: URIRef, field: str) -> str:
    term = _only(graph, subject, _property(field))
    if not isinstance(term, Literal) or term.language or term.datatype not in (None, XSD_NS.string):
        raise RDFInteroperabilityError(f'{field} must be an RDF string')
    return str(term)


def _metadata(graph: Graph, subject: URIRef, field: str) -> dict:
    try:
        value = parse(_text(graph, subject, field).encode('utf-8'))
    except (GraphStoreError, ValueError, UnicodeError) as exc:
        raise RDFInteroperabilityError('Invalid canonical JSON metadata') from exc
    if not isinstance(value, dict):
        raise RDFInteroperabilityError('Attributes and metadata must be JSON objects')
    return value


def _integer(graph: Graph, subject: URIRef, field: str) -> int:
    term = _only(graph, subject, _property(field))
    if not isinstance(term, Literal) or term.datatype != XSD_NS.nonNegativeInteger:
        raise RDFInteroperabilityError('Occurrence must be xsd:nonNegativeInteger')
    if not str(term).isdigit() or (len(str(term)) > 1 and str(term)[0] == '0'):
        raise RDFInteroperabilityError('Noncanonical occurrence lexical form')
    return int(str(term))


def _false(graph: Graph, subject: URIRef, field: str) -> None:
    term = _only(graph, subject, _property(field))
    if not isinstance(term, Literal) or term.datatype != XSD_NS.boolean or str(term) != 'false':
        raise RDFInteroperabilityError(f'{field} must be explicitly false')


def _read_rdf(bundle: dict) -> Graph:
    try:
        parsed_nt = Graph().parse(data=bundle['ntriples'].decode('utf-8'), format='nt')
        parsed_ttl = Graph().parse(data=bundle['turtle'].decode('utf-8'), format='turtle')
    except Exception as exc:
        # RDFLib may expose several parse-error types depending on syntax.
        raise RDFInteroperabilityError('An RDF serialization cannot be parsed') from exc
    if (not parsed_nt or len(parsed_nt) > MAX_TRIPLES or len(parsed_ttl) > MAX_TRIPLES
            or set(parsed_nt) != set(parsed_ttl)):
        raise RDFInteroperabilityError('RDF representations have different triple sets')
    if any(not isinstance(s, URIRef) or not isinstance(p, URIRef) or
           not isinstance(o, (URIRef, Literal)) for s, p, o in parsed_nt):
        raise RDFInteroperabilityError('Unexpected RDF terms or blank nodes')
    return parsed_nt


def _reconstruct(graph: Graph, source_view) -> tuple[list[dict], list[dict]]:
    graph_iri = _uri('snapshot', source_view.fingerprint)
    if (set(graph.subjects(RDF_NS.type, _uri('type', 'GraphSnapshot'))) != {graph_iri}
            or _text(graph, graph_iri, 'domain') != source_view.domain
            or _text(graph, graph_iri, 'graphFingerprint') != source_view.fingerprint
            or _text(graph, graph_iri, 'inputSha256') != source_view.input_sha256):
        raise RDFInteroperabilityError('RDF graph identity does not match verified GE view')
    for field in ('scientificTruthEstablished', 'automaticApprovalPermitted',
                  'authoritativeMutationPermitted'):
        _false(graph, graph_iri, field)

    node_resources = list(graph.objects(graph_iri, _property('containsNode')))
    edge_resources = list(graph.objects(graph_iri, _property('containsEdge')))
    if len(node_resources) != len(set(node_resources)) or len(edge_resources) != len(set(edge_resources)):
        raise RDFInteroperabilityError('Repeated resource identity')
    nodes = []
    known = set()
    resource_ids = {}
    for resource in node_resources:
        ident = _text(graph, resource, 'nodeIdentifier')
        typ = _text(graph, resource, 'entityType')
        if resource != _uri('node', ident) or not ident or not typ or ident in known:
            raise RDFInteroperabilityError('Invalid or repeated node identity')
        known.add(ident)
        resource_ids[resource] = ident
        if _only(graph, resource, RDF_NS.type) != _uri('type', typ):
            raise RDFInteroperabilityError('Mismatched node RDF type')
        nodes.append({'id': ident, 'type': typ,
                      'attributes': _metadata(graph, resource, 'attributesJson'),
                      'metadata': _metadata(graph, resource, 'metadataJson')})
    edges = []
    occurrences: dict[bytes, set[int]] = {}
    for resource in edge_resources:
        if _only(graph, resource, RDF_NS.type) != RDF_NS.Statement:
            raise RDFInteroperabilityError('Missing RDF Statement edge reification')
        src = _only(graph, resource, RDF_NS.subject)
        dst = _only(graph, resource, RDF_NS.object)
        relation_iri = _only(graph, resource, RDF_NS.predicate)
        relation = _text(graph, resource, 'relationType')
        occurrence = _integer(graph, resource, 'parallelEdgeOccurrence')
        attrs = _metadata(graph, resource, 'attributesJson')
        meta = _metadata(graph, resource, 'metadataJson')
        if not relation or relation_iri != _uri('relation', relation):
            raise RDFInteroperabilityError('Invalid reified relation predicate')
        # Exact resource lookup is linear overall, even for large multigraphs.
        if src not in resource_ids or dst not in resource_ids:
            raise RDFInteroperabilityError('Reified edge references missing nodes')
        record = {'source': resource_ids[src], 'target': resource_ids[dst],
                  'relation': relation, 'attributes': attrs, 'metadata': meta}
        payload = canonical(record)
        expected_resource = _uri('edge', f'{_sha(payload)}:{occurrence}')
        if resource != expected_resource or (src, relation_iri, dst) not in graph:
            raise RDFInteroperabilityError('RDF edge identity or direct relation mismatch')
        occurrences.setdefault(payload, set())
        if occurrence in occurrences[payload]:
            raise RDFInteroperabilityError('Duplicate edge occurrence identifier')
        occurrences[payload].add(occurrence)
        _false(graph, resource, 'scientificSupportVerified')
        edges.append(record)
    for payload, indices in occurrences.items():
        if indices != set(range(len(indices))):
            raise RDFInteroperabilityError('Noncontiguous parallel edge occurrence indices')
    return nodes, edges


def _records_equal(generated: list[dict], original: list[dict]) -> bool:
    return Counter(canonical(x) for x in generated) == Counter(canonical(x) for x in original)


def verify_rdf_interoperability(source_view, bundle: dict, *, store_state: dict | None = None) -> dict:
    """Verify external RDF against verified graph, preserving multigraph details."""
    manifest = bundle.get('manifest')
    if not isinstance(manifest, dict) or manifest.get('schema_version') != 'g4-rdf-export/v1':
        raise RDFInteroperabilityError('Unsupported RDF export schema')
    if any(manifest.get(key) is not False for key in (
        'scientific_truth_established', 'automatic_approval_permitted',
        'authoritative_graph_mutation_permitted', 'rdf_semantic_entailment_verified',
        'round_trip_semantic_approval')):
        raise RDFInteroperabilityError('Unsafe manifest authority claims')
    if _sha(canonical({k: v for k, v in manifest.items() if k != 'manifest_sha256'})) != manifest.get('manifest_sha256'):
        raise RDFInteroperabilityError('Corrupted RDF export manifest')
    for member, field in [('ntriples', 'ntriples_sha256'), ('turtle', 'turtle_sha256')]:
        if not isinstance(bundle.get(member), bytes) or _sha(bundle[member]) != manifest.get(field):
            raise RDFInteroperabilityError('RDF file digest mismatch')
    parsed = _read_rdf(bundle)
    nodes, edges = _reconstruct(parsed, source_view)
    source = source_view.graph.to_dict()
    if not _records_equal(nodes, source['nodes']) or not _records_equal(edges, source['edges']):
        raise RDFInteroperabilityError('RDF inverse projection differs from verified graph structure')
    # Compare complete parsed graphs, not just selected vocabulary: injected
    # triples and removed direct/reification relations must be rejected.
    expected = export_view(source_view, store_state=store_state)
    if manifest != expected['manifest'] or set(parsed) != set(_read_rdf(expected)):
        raise RDFInteroperabilityError('Unrecognized RDF triples or source provenance mismatch')
    # Enforce exact published canonical representations as well as equivalence.
    if any(bundle[key] != expected[key] for key in ('ntriples', 'turtle')):
        raise RDFInteroperabilityError('Noncanonical RDF serialization differs from verified export')
    report = {
        'schema_version': SCHEMA,
        'source_graph_fingerprint': source_view.fingerprint,
        'source_snapshot_sha256': source_view.snapshot()['snapshot_sha256'],
        'source_input_sha256': source_view.input_sha256,
        'persisted_store_head': store_state['head'] if store_state else None,
        'persisted_store_generation': store_state['generation'] if store_state else None,
        'rdf_export_manifest_sha256': manifest['manifest_sha256'],
        'ntriples_sha256': manifest['ntriples_sha256'],
        'turtle_sha256': manifest['turtle_sha256'],
        'triple_count': len(parsed), 'node_count': len(nodes),
        'edge_occurrence_count': len(edges),
        'independent_rdf_parser_equivalence': True,
        'attributed_multigraph_structure_preserved': True,
        'semantic_entailment_verified': False,
        'scientific_truth_established': False,
        'automatic_approval_permitted': False,
        'authoritative_graph_mutation_permitted': False,
    }
    report['report_sha256'] = _sha(canonical(report))
    return report


def verify_directory(repository: Path, export_dir: Path, *, mode: str = 'persisted',
                     knowledge_graph: str | None = None) -> dict:
    """Read but never change a source repository or export directory."""
    repo = Path(repository).resolve(strict=True)
    if mode == 'persisted':
        state_store = PersistentDomainGraphStore(repo/'.graph-state/scientific')
        state = state_store.verify()
        if state.get('status') != 'verified':
            raise RDFInteroperabilityError('No verified persisted GE-02 state')
        view = state_store.current_view()
        if view is None:
            raise RDFInteroperabilityError('Persisted GE state has no view')
    elif mode == 'candidate':
        if not knowledge_graph:
            raise RDFInteroperabilityError('Missing candidate knowledge graph')
        from audit_engine.semantic_audit.graph.domain_integration import _read_json
        view = from_scientific_graph(_read_json(_input_path(repo, knowledge_graph)))
        state = None
    else:
        raise RDFInteroperabilityError('Unknown verification mode')
    return verify_rdf_interoperability(view, read_export(Path(export_dir)), store_state=state)


def _write_report(path: Path, repository: Path, report: dict):
    dest = Path(path).absolute()
    repo = repository.resolve(strict=True)
    if dest == repo or repo in dest.parents or dest.is_symlink() or dest.exists():
        raise RDFInteroperabilityError('Report must be a new file outside the repository')
    if not dest.parent.is_dir() or any(p.is_symlink() for p in (dest.parent, *dest.parents)):
        raise RDFInteroperabilityError('Unsafe report output parent')
    raw = canonical(report)
    if len(raw) > REPORT_MAX_BYTES:
        raise RDFInteroperabilityError('Report too large')
    _new_file(dest, raw)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='G4.6 source-bound read-only RDF interoperability audit')
    parser.add_argument('--repository', required=True)
    parser.add_argument('--export-dir', required=True)
    parser.add_argument('--mode', choices=('persisted', 'candidate'), default='persisted')
    parser.add_argument('--knowledge-graph')
    parser.add_argument('--report', required=True)
    args = parser.parse_args(argv)
    report = verify_directory(Path(args.repository), Path(args.export_dir), mode=args.mode,
                              knowledge_graph=args.knowledge_graph)
    _write_report(Path(args.report), Path(args.repository), report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (RDFInteroperabilityError, RDFExportError, GraphStoreError,
            GraphDomainError, ValueError, TypeError, OSError, KeyError) as exc:
        print('G4 RDF interoperability rejected:', exc, file=__import__('sys').stderr)
        raise SystemExit(2)
