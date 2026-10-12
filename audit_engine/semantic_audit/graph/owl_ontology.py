"""G5.1: source-bound OWL/RDFS vocabulary for the verified GE -> G4 RDF graph.

Produces a read-only OWL schema and a union graph suitable for independent RDF
clients. No OWL reasoner, science entailment, user-supplied imports, or graph writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS, OWL, XSD

from audit_engine.semantic_audit.graph.domain_integration import GraphDomainError, from_scientific_graph
from audit_engine.semantic_audit.graph.persistent_domain_state import (
    GraphStoreError, PersistentDomainGraphStore, canonical, parse, _input_path,
)
from audit_engine.semantic_audit.graph.rdf_export import (
    RDFExportError, NS, MAX_BYTES, MAX_TRIPLES, export_view, _output_dir, _new_file, _read_regular,
)
from audit_engine.semantic_audit.graph.rdf_interoperability import (
    RDFInteroperabilityError, verify_rdf_interoperability, _read_rdf,
)

SCHEMA = 'g5-owl-vocabulary/v1'
ONTOLOGY = URIRef('urn:fea:ontology:v1')
OWL_NS = 'urn:fea:owl:v1:'
MAX_ONTOLOGY_TRIPLES = 25_000
MAX_REPORT_BYTES = 32_768


class OWLOntologyError(ValueError):
    """A source-bound OWL projection is invalid or cannot be verified."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _iri(kind: str, value: str) -> URIRef:
    return URIRef(NS + quote(kind + ':' + value, safe=''))


def _prop(key: str) -> URIRef:
    return URIRef(OWL_NS + key)


def _parse_nt(data: bytes) -> Graph:
    try:
        graph = Graph().parse(data=data.decode('utf-8'), format='nt')
    except Exception as exc:
        raise OWLOntologyError('Malformed OWL graph') from exc
    if not graph or len(graph) > MAX_TRIPLES + MAX_ONTOLOGY_TRIPLES:
        raise OWLOntologyError('Invalid OWL graph size')
    return graph


def _serialization(triples: Graph) -> tuple[bytes, bytes]:
    if len(triples) > MAX_TRIPLES + MAX_ONTOLOGY_TRIPLES:
        raise OWLOntologyError('Ontology triple count exceeds limit')
    lines = []
    for s, p, o in triples:
        if not isinstance(s, URIRef) or not isinstance(p, URIRef) or not isinstance(o, (URIRef, Literal)):
            raise OWLOntologyError('Blank nodes or unsupported terms are prohibited')
        # RDFLib's term.n3() properly quotes Unicode and typed literals.
        lines.append(f'{s.n3()} {p.n3()} {o.n3()} .\n')
    nt = ''.join(sorted(lines)).encode('utf-8')
    # Canonical N-Triples statements are also legal Turtle. No unstable
    # QName compaction or unsorted RDFLib serialization is involved.
    ttl = (f'@prefix owl: <{OWL}> .\n@prefix rdfs: <{RDFS}> .\n'
           f'@prefix rdf: <{RDF}> .\n@prefix xsd: <{XSD}> .\n\n').encode('ascii') + nt
    if max(len(nt), len(ttl)) > MAX_BYTES:
        raise OWLOntologyError('Ontology output exceeds byte limit')
    return nt, ttl


def _owl_schema(view, rdf_bundle: dict) -> Graph:
    graph = Graph()
    add = graph.add
    add((ONTOLOGY, RDF.type, OWL.Ontology))
    add((ONTOLOGY, RDFS.label, Literal('Finite Element Analysis verified graph vocabulary', lang='en')))
    add((ONTOLOGY, OWL.versionInfo, Literal('G5.1: structural ontology, no entailment claims')))
    # Provenance annotation properties apply to this projected ontology dataset.
    for name in ('sourceGraphFingerprint', 'sourceSnapshotSha256', 'sourceInputSha256',
                 'rdfExportManifestSha256', 'scientificTruthEstablished',
                 'owlEntailmentVerified', 'automaticApprovalPermitted',
                 'authoritativeGraphMutationPermitted'):
        add((_prop(name), RDF.type, OWL.AnnotationProperty))
    metadata = {
        'sourceGraphFingerprint': view.fingerprint,
        'sourceSnapshotSha256': view.snapshot()['snapshot_sha256'],
        'sourceInputSha256': view.input_sha256,
        'rdfExportManifestSha256': rdf_bundle['manifest']['manifest_sha256'],
    }
    for key, value in metadata.items():
        add((ONTOLOGY, _prop(key), Literal(value, datatype=XSD.string)))
    for key in ('scientificTruthEstablished', 'owlEntailmentVerified',
                'automaticApprovalPermitted', 'authoritativeGraphMutationPermitted'):
        add((ONTOLOGY, _prop(key), Literal(False, datatype=XSD.boolean)))

    entity = _iri('type', 'SemanticEntity')
    snapshot = _iri('type', 'GraphSnapshot')
    add((entity, RDF.type, OWL.Class))
    add((snapshot, RDF.type, OWL.Class))

    classes = {node.entity_type for node in view.graph.nodes}
    # Construct classes only for actually present node types, keeping vocabulary
    # explicit and avoiding unsupported 'all entities have this type' inference.
    for name in sorted(classes):
        if not isinstance(name, str) or not name or len(name) > 1024:
            raise OWLOntologyError('Invalid scientific class name')
        resource = _iri('type', name)
        add((resource, RDF.type, OWL.Class))
        if resource != entity and resource != snapshot:
            add((resource, RDFS.subClassOf, entity))

    # Explicitly type only properties that the G4 v1 exporter emits. The
    # OWL object/data property separation preserves observed RDF term kinds.
    object_properties = {'containsNode', 'containsEdge'}
    datatype_properties = {
        'domain', 'graphFingerprint', 'inputSha256', 'snapshotSha256',
        'scientificTruthEstablished', 'automaticApprovalPermitted',
        'authoritativeMutationPermitted', 'persistedHead', 'persistedGeneration',
        'nodeIdentifier', 'entityType', 'attributesJson', 'metadataJson',
        'relationType', 'parallelEdgeOccurrence', 'scientificSupportVerified',
    }
    for name in sorted(object_properties):
        add((_iri('property', name), RDF.type, OWL.ObjectProperty))
    for name in sorted(datatype_properties):
        add((_iri('property', name), RDF.type, OWL.DatatypeProperty))
    for name in sorted({edge.relation_type for edge in view.graph.edges}):
        if not isinstance(name, str) or not name or len(name) > 1024:
            raise OWLOntologyError('Invalid scientific relation type')
        add((_iri('relation', name), RDF.type, OWL.ObjectProperty))

    # An occurrence is an RDF reified Statement in G4's published vocabulary.
    # No property chains, sameAs, disjointness or domain/range inference are
    # introduced; these would require a separate ontology-review gate.
    return graph


def build_owl_layer(view, rdf_bundle: dict, *, store_state: dict | None = None) -> dict:
    """Independently verify G4 and build deterministic OWL/RDF ontology bytes."""
    try:
        report = verify_rdf_interoperability(view, rdf_bundle, store_state=store_state)
    except (RDFInteroperabilityError, RDFExportError, GraphStoreError, GraphDomainError) as exc:
        raise OWLOntologyError('G4 RDF source-bound verification failed') from exc
    schema = _owl_schema(view, rdf_bundle)
    source = _read_rdf(rdf_bundle)
    combined = Graph()
    for triple in source:
        combined.add(triple)
    for triple in schema:
        combined.add(triple)
    schema_nt, schema_ttl = _serialization(schema)
    combined_nt, combined_ttl = _serialization(combined)
    # Parse both published syntaxes independently before claiming parsing verified.
    for nt, ttl in ((schema_nt, schema_ttl), (combined_nt, combined_ttl)):
        try:
            parsed_ttl = Graph().parse(data=ttl.decode('utf-8'), format='turtle')
        except Exception as exc:
            raise OWLOntologyError('Generated OWL Turtle failed independent parsing') from exc
        if set(_parse_nt(nt)) != set(parsed_ttl):
            raise OWLOntologyError('Generated OWL serializations disagree')
    manifest = {
        'schema_version': SCHEMA,
        'source_graph_fingerprint': view.fingerprint,
        'source_snapshot_sha256': view.snapshot()['snapshot_sha256'],
        'source_input_sha256': view.input_sha256,
        'persisted_store_head': report['persisted_store_head'],
        'persisted_store_generation': report['persisted_store_generation'],
        'g4_manifest_sha256': rdf_bundle['manifest']['manifest_sha256'],
        'g4_triple_count': len(source),
        'ontology_triple_count': len(schema),
        'combined_triple_count': len(combined),
        'declared_graph_node_classes': sorted({n.entity_type for n in view.graph.nodes}),
        'declared_graph_relation_properties': sorted({e.relation_type for e in view.graph.edges}),
        'owl_ontology_parsing_verified': True,
        'g4_structural_equivalence_verified': True,
        'owl_entailment_verified': False,
        'scientific_truth_established': False,
        'automatic_approval_permitted': False,
        'authoritative_graph_mutation_permitted': False,
    }
    blob = {'ontology_nt': schema_nt, 'ontology_ttl': schema_ttl,
            'combined_nt': combined_nt, 'combined_ttl': combined_ttl}
    for key, data in blob.items():
        manifest[key + '_sha256'] = _sha(data)
    manifest['manifest_sha256'] = _sha(canonical(manifest))
    blob['manifest'] = manifest
    return blob


def verify_owl_layer(view, rdf_bundle: dict, bundle: dict, *, store_state: dict | None = None) -> dict:
    """Fail closed if the ontology diverges from a verified G4 source.

    Reproducibility requires complete bytes and manifests, not just hashes that
    an attacker could recompute. Also check each RDFLib parsed triple set.
    """
    expected = build_owl_layer(view, rdf_bundle, store_state=store_state)
    if not isinstance(bundle, dict) or set(bundle) != set(expected):
        raise OWLOntologyError('Missing or unexpected OWL artifact member')
    for key in expected:
        if bundle[key] != expected[key]:
            raise OWLOntologyError('OWL content differs from verified source: ' + key)
    for nt_name, ttl_name in (('ontology_nt', 'ontology_ttl'), ('combined_nt', 'combined_ttl')):
        nt = _parse_nt(bundle[nt_name])
        try:
            ttl = Graph().parse(data=bundle[ttl_name].decode('utf-8'), format='turtle')
        except Exception as exc:
            raise OWLOntologyError('Malformed OWL Turtle') from exc
        if set(nt) != set(ttl):
            raise OWLOntologyError('Independent OWL RDF syntax disagreement')
        if (ONTOLOGY, RDF.type, OWL.Ontology) not in nt:
            raise OWLOntologyError('Missing OWL ontology assertion')
        forbidden = {OWL.imports, OWL.sameAs, OWL.equivalentClass,
                     OWL.equivalentProperty, OWL.propertyChainAxiom,
                     OWL.inverseOf, OWL.disjointWith, OWL.hasKey}
        if any(p in forbidden for _, p, _ in nt):
            raise OWLOntologyError('Unauthorized OWL reasoning axiom')
    source = _read_rdf(rdf_bundle)
    schema = _parse_nt(bundle['ontology_nt'])
    combined = _parse_nt(bundle['combined_nt'])
    if set(combined) != set(schema) | set(source):
        raise OWLOntologyError('OWL knowledge graph does not match G4 source union')
    return expected['manifest']


_NAMES = {
    'ontology_nt': 'ontology-schema.nt',
    'ontology_ttl': 'ontology-schema.ttl',
    'combined_nt': 'ontology-knowledge-graph.nt',
    'combined_ttl': 'ontology-knowledge-graph.ttl',
    'manifest': 'owl-export-manifest.json',
}


def _verified_view(repository: Path, mode: str, knowledge_graph: str | None):
    if mode == 'persisted':
        store = PersistentDomainGraphStore(repository/'.graph-state/scientific')
        state = store.verify()
        if state.get('status') != 'verified':
            raise OWLOntologyError('Missing verified GE-02 persisted state')
        view = store.current_view()
        if view is None:
            raise OWLOntologyError('No persisted graph view')
        return view, state
    if mode == 'candidate':
        if not knowledge_graph:
            raise OWLOntologyError('Candidate requires knowledge graph path')
        from audit_engine.semantic_audit.graph.domain_integration import _read_json
        try:
            return from_scientific_graph(_read_json(_input_path(repository, knowledge_graph))), None
        except (GraphDomainError, GraphStoreError, OSError, ValueError, UnicodeError) as exc:
            raise OWLOntologyError("Missing, unsafe, or invalid candidate graph") from exc
    raise OWLOntologyError('Unsupported source mode')


def write_owl_directory(repository: Path, destination: Path, *, mode: str = 'persisted',
                        knowledge_graph: str | None = None) -> dict:
    repo = Path(repository).resolve(strict=True)
    target = _output_dir(Path(destination), repo)
    view, state = _verified_view(repo, mode, knowledge_graph)
    rdf = export_view(view, store_state=state)
    bundle = build_owl_layer(view, rdf, store_state=state)
    verify_owl_layer(view, rdf, bundle, store_state=state)
    target.mkdir(mode=0o700)
    for key, filename in _NAMES.items():
        _new_file(target/filename, canonical(bundle[key]) if key == 'manifest' else bundle[key])
    verify_owl_layer(view, rdf, read_owl_directory(target), store_state=state)
    return bundle['manifest']


def read_owl_directory(directory: Path) -> dict:
    path = Path(directory)
    result = {}
    for key, name in _NAMES.items():
        data = _read_regular(path/name, 20_480 if key == 'manifest' else MAX_BYTES)
        result[key] = parse(data) if key == 'manifest' else data
    return result


def verify_owl_directory(repository: Path, directory: Path, *, mode: str = 'persisted',
                         knowledge_graph: str | None = None) -> dict:
    repo = Path(repository).resolve(strict=True)
    view, state = _verified_view(repo, mode, knowledge_graph)
    return verify_owl_layer(view, export_view(view, store_state=state),
                            read_owl_directory(directory), store_state=state)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='G5.1 source-bound read-only OWL vocabulary')
    parser.add_argument('command', choices=('build', 'verify'))
    parser.add_argument('--repository', required=True)
    parser.add_argument('--mode', choices=('persisted', 'candidate'), default='persisted')
    parser.add_argument('--knowledge-graph')
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--report')
    args = parser.parse_args(argv)
    if args.command == 'build':
        result = write_owl_directory(Path(args.repository), Path(args.output_dir),
                                     mode=args.mode, knowledge_graph=args.knowledge_graph)
    else:
        result = verify_owl_directory(Path(args.repository), Path(args.output_dir),
                                      mode=args.mode, knowledge_graph=args.knowledge_graph)
    if args.report:
        if args.command != 'verify':
            raise OWLOntologyError('Detached report is supported only for verification')
        repo = Path(args.repository).resolve(strict=True)
        output = Path(args.report).absolute()
        if (output.exists() or output.is_symlink() or output == repo or repo in output.parents
                or not output.parent.is_dir() or any(p.is_symlink() for p in output.parents)):
            raise OWLOntologyError('Unsafe detached report output path')
        report = {'schema_version': 'g5-owl-validation/v1',
                  'source_manifest_sha256': result['manifest_sha256'],
                  'ontology_triple_count': result['ontology_triple_count'],
                  'combined_triple_count': result['combined_triple_count'],
                  'source_bound_owl_parsing_verified': True,
                  'scientific_truth_established': False,
                  'owl_entailment_verified': False,
                  'automatic_approval_permitted': False,
                  'authoritative_graph_mutation_permitted': False}
        report['report_sha256'] = _sha(canonical(report))
        raw = canonical(report)
        if len(raw) > MAX_REPORT_BYTES:
            raise OWLOntologyError('Report exceeds byte limit')
        _new_file(output, raw)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OWLOntologyError, RDFExportError, RDFInteroperabilityError,
            GraphStoreError, GraphDomainError, OSError, ValueError, TypeError, KeyError) as exc:
        print('G5 OWL vocabulary rejected:', exc, file=__import__('sys').stderr)
        raise SystemExit(2)
