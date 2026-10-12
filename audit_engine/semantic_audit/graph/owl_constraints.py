"""G5.2: trusted OWL structural profile and independently checked instance conformance.

OWL domain/range axioms carry *inference semantics*, not closed-world constraints.
The local conformance verifier is deliberately distinct from OWL entailment,
scientific truth, SAT authorization, or ontology reasoner consistency.
No remote RDF import, schema upload, graph update, or unchecked inference.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS, OWL, XSD

from audit_engine.semantic_audit.graph.domain_integration import GraphDomainError
from audit_engine.semantic_audit.graph.persistent_domain_state import (
    GraphStoreError, canonical, parse,
)
from audit_engine.semantic_audit.graph.rdf_export import (
    RDFExportError, export_view, _output_dir, _new_file, _read_regular, MAX_BYTES,
)
from audit_engine.semantic_audit.graph.rdf_interoperability import RDFInteroperabilityError
from audit_engine.semantic_audit.graph.owl_ontology import (
    OWLOntologyError, ONTOLOGY, _iri, _prop, _serialization, _parse_nt,
    _verified_view, build_owl_layer, verify_owl_layer,
)

SCHEMA = 'g5-owl-structural-constraints/v1'
REPORT_SCHEMA = 'g5-owl-structural-conformance/v1'
MAX_REPORT_BYTES = 32768

class OWLConstraintError(ValueError):
    """A source-bound OWL constraint or conformance contract was violated."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# This is a fixed, reviewed structural profile. No scientific relationship
# direction or external ontology axioms are inferred from untrusted inputs.
# rdf:Statement denotes G4's reified edge occurrences.
DECLARATIONS = (
    ('containsNode', _iri('type', 'GraphSnapshot'), _iri('type', 'SemanticEntity')),
    ('containsEdge', _iri('type', 'GraphSnapshot'), RDF.Statement),
    ('nodeIdentifier', _iri('type', 'SemanticEntity'), XSD.string),
    ('entityType', _iri('type', 'SemanticEntity'), XSD.string),
    ('relationType', RDF.Statement, XSD.string),
    ('parallelEdgeOccurrence', RDF.Statement, XSD.nonNegativeInteger),
    ('scientificSupportVerified', RDF.Statement, XSD.boolean),
    ('persistedGeneration', _iri('type', 'GraphSnapshot'), XSD.nonNegativeInteger),
    ('graphFingerprint', _iri('type', 'GraphSnapshot'), XSD.string),
    ('snapshotSha256', _iri('type', 'GraphSnapshot'), XSD.string),
    ('scientificTruthEstablished', _iri('type', 'GraphSnapshot'), XSD.boolean),
    ('automaticApprovalPermitted', _iri('type', 'GraphSnapshot'), XSD.boolean),
    ('authoritativeMutationPermitted', _iri('type', 'GraphSnapshot'), XSD.boolean),
    ('attributesJson', None, XSD.string),  # shared by nodes and reified edges
    ('metadataJson', None, XSD.string),
)


def _axiom_graph(base_manifest: dict) -> Graph:
    axioms = Graph()
    axioms.add((ONTOLOGY, RDFS.comment, Literal(
        'G5.2 structural domain/range semantics; conformance separately checked; '
        'no scientific entailment or automatic approval', lang='en')))
    axioms.add((_prop('constraintProfileSourceManifest'), RDF.type, OWL.AnnotationProperty))
    axioms.add((ONTOLOGY, _prop('constraintProfileSourceManifest'),
                Literal(base_manifest['manifest_sha256'], datatype=XSD.string)))
    for name, domain, rng in DECLARATIONS:
        predicate = _iri('property', name)
        if domain is not None:
            axioms.add((predicate, RDFS.domain, domain))
        axioms.add((predicate, RDFS.range, rng))
    return axioms


def _member_of(graph: Graph, subject, expected_type: URIRef) -> bool:
    if (subject, RDF.type, expected_type) in graph:
        return True
    # Exact, finite subclass closure over the G5.1 source-bound declarations.
    stack = list(graph.objects(subject, RDF.type))
    seen = set()
    while stack:
        typ = stack.pop()
        if typ == expected_type:
            return True
        if typ in seen:
            continue
        seen.add(typ)
        if len(seen) > 25000:
            raise OWLConstraintError('Unbounded class ancestry')
        stack.extend(graph.objects(typ, RDFS.subClassOf))
    return False


def _object_matches(obj, range_type: URIRef, graph: Graph) -> bool:
    if range_type in (XSD.string, XSD.boolean, XSD.nonNegativeInteger):
        if not isinstance(obj, Literal) or obj.language:
            return False
        if range_type == XSD.string:
            return obj.datatype in (None, XSD.string)
        if obj.datatype != range_type:
            return False
        lexical = str(obj)
        if range_type == XSD.boolean:
            return lexical in ('true', 'false')
        return bool(lexical) and lexical.isascii() and lexical.isdigit() and (
            lexical == '0' or lexical[0] != '0')
    return isinstance(obj, URIRef) and _member_of(graph, obj, range_type)


def audit_structural_conformance(combined: Graph, *, expected_nodes: int, expected_edges: int,
                                 persisted: bool) -> dict:
    """Check finite, source-bound RDF structural shapes; NOT OWL reasoning."""
    if not isinstance(combined, Graph) or len(combined) > 275000:
        raise OWLConstraintError('Unsafe combined graph size')
    typed_snapshots = set(combined.subjects(RDF.type, _iri('type', 'GraphSnapshot')))
    if len(typed_snapshots) != 1:
        raise OWLConstraintError('Exactly one graph snapshot is required')
    snap = next(iter(typed_snapshots))
    audited = 0
    by_property = {}
    for name, domain, rng in DECLARATIONS:
        predicate = _iri('property', name)
        pairs = list(combined.subject_objects(predicate))
        for sub, obj in pairs:
            if domain is not None and not _member_of(combined, sub, domain):
                raise OWLConstraintError('Declared domain failed: ' + name)
            if not _object_matches(obj, rng, combined):
                raise OWLConstraintError('Declared range failed: ' + name)
            # The profile disallows accidental escalation through open-world RDF.
            if name in ('scientificTruthEstablished', 'automaticApprovalPermitted',
                        'authoritativeMutationPermitted', 'scientificSupportVerified') and str(obj) != 'false':
                raise OWLConstraintError('Forbidden authority flag')
        by_property[name] = len(pairs)
        audited += len(pairs)
    if (by_property['containsNode'] != expected_nodes or
        by_property['containsEdge'] != expected_edges or
        by_property['nodeIdentifier'] != expected_nodes or
        by_property['entityType'] != expected_nodes or
        by_property['relationType'] != expected_edges or
        by_property['parallelEdgeOccurrence'] != expected_edges or
        by_property['scientificSupportVerified'] != expected_edges or
        by_property['attributesJson'] != expected_nodes + expected_edges or
        by_property['metadataJson'] != expected_nodes + expected_edges):
        raise OWLConstraintError('Incomplete node or edge structural coverage')
    for name in ('scientificTruthEstablished', 'automaticApprovalPermitted',
                 'authoritativeMutationPermitted', 'graphFingerprint', 'snapshotSha256'):
        if by_property[name] != 1:
            raise OWLConstraintError('Missing snapshot property: ' + name)
    if by_property['persistedGeneration'] != (1 if persisted else 0):
        raise OWLConstraintError('Persisted-generation shape mismatch')
    # Verify membership and edge fields are attached to the same subjects,
    # not merely matching aggregate triple counts.
    nodes = set(combined.objects(snap, _iri('property', 'containsNode')))
    edges = set(combined.objects(snap, _iri('property', 'containsEdge')))
    if len(nodes) != expected_nodes or len(edges) != expected_edges or nodes & edges:
        raise OWLConstraintError('Invalid node/edge membership')
    for node in nodes:
        for name in ('nodeIdentifier', 'entityType', 'attributesJson', 'metadataJson'):
            if len(list(combined.objects(node, _iri('property', name)))) != 1:
                raise OWLConstraintError('Node lacks unique structural field: ' + name)
    for edge in edges:
        for name in ('relationType', 'parallelEdgeOccurrence', 'scientificSupportVerified',
                     'attributesJson', 'metadataJson'):
            if len(list(combined.objects(edge, _iri('property', name)))) != 1:
                raise OWLConstraintError('Edge lacks unique structural field: ' + name)
        for name in (RDF.subject, RDF.predicate, RDF.object):
            if len(list(combined.objects(edge, name))) != 1:
                raise OWLConstraintError('Reified edge lacks unique RDF field')
    return {'structural_property_occurrences_audited': audited,
            'covered_node_count': len(nodes), 'covered_edge_occurrence_count': len(edges),
            'constrained_property_count': len(DECLARATIONS), 'finite_structural_conformance': True}


def build_constraint_layer(view, rdf_bundle: dict, base_owl: dict,
                           *, store_state: dict | None = None) -> dict:
    try:
        verify_owl_layer(view, rdf_bundle, base_owl, store_state=store_state)
        base = _parse_nt(base_owl['combined_nt'])
        axioms = _axiom_graph(base_owl['manifest'])
        checked = audit_structural_conformance(
            base, expected_nodes=len(view.graph.nodes), expected_edges=len(view.graph.edges),
            persisted=store_state is not None)
        combined = Graph()
        for triple in base:
            combined.add(triple)
        for triple in axioms:
            combined.add(triple)
        ax_nt, ax_ttl = _serialization(axioms)
        full_nt, full_ttl = _serialization(combined)
        for nt, ttl in ((ax_nt, ax_ttl), (full_nt, full_ttl)):
            parsed = Graph().parse(data=ttl.decode('utf-8'), format='turtle')
            if set(_parse_nt(nt)) != set(parsed):
                raise OWLConstraintError('Serialization mismatch')
    except (OWLOntologyError, RDFInteroperabilityError, RDFExportError,
            GraphStoreError, GraphDomainError, UnicodeError, ValueError) as exc:
        raise OWLConstraintError('Cannot derive verified G5.2 layer') from exc
    manifest = {
        'schema_version': SCHEMA,
        'source_graph_fingerprint': view.fingerprint,
        'source_snapshot_sha256': view.snapshot()['snapshot_sha256'],
        'source_g5_manifest_sha256': base_owl['manifest']['manifest_sha256'],
        'source_g4_manifest_sha256': rdf_bundle['manifest']['manifest_sha256'],
        'persisted_store_head': store_state['head'] if store_state else None,
        'persisted_store_generation': store_state['generation'] if store_state else None,
        **checked,
        'owl_domain_range_axioms_present': True,
        'owl_reasoner_consistency_verified': False,
        'owl_entailment_verified': False,
        'scientific_truth_established': False,
        'automatic_approval_permitted': False,
        'authoritative_graph_mutation_permitted': False,
    }
    bundle = {'axioms_nt': ax_nt, 'axioms_ttl': ax_ttl,
              'combined_nt': full_nt, 'combined_ttl': full_ttl}
    for name, blob in bundle.items():
        manifest[name + '_sha256'] = _sha(blob)
    manifest['manifest_sha256'] = _sha(canonical(manifest))
    bundle['manifest'] = manifest
    return bundle


def verify_constraint_layer(view, rdf_bundle: dict, base_owl: dict, bundle: dict,
                            *, store_state: dict | None = None) -> dict:
    expected = build_constraint_layer(view, rdf_bundle, base_owl, store_state=store_state)
    if not isinstance(bundle, dict) or set(bundle) != set(expected):
        raise OWLConstraintError('Missing or unexpected ontology artifacts')
    for name, item in expected.items():
        if bundle[name] != item:
            raise OWLConstraintError('Source-bound ontology mismatch: ' + name)
    for name in ('axioms', 'combined'):
        nt = _parse_nt(bundle[name + '_nt'])
        ttl = Graph().parse(data=bundle[name + '_ttl'].decode('utf-8'), format='turtle')
        if set(nt) != set(ttl):
            raise OWLConstraintError('Independent RDF formats disagree')
        if any(p in {OWL.imports, OWL.sameAs, OWL.equivalentClass,
                     OWL.equivalentProperty, OWL.propertyChainAxiom, OWL.inverseOf,
                     OWL.disjointWith, OWL.hasKey} for _, p, _ in nt):
            raise OWLConstraintError('Unapproved ontology axiom')
    full = _parse_nt(bundle['combined_nt'])
    base = _parse_nt(base_owl['combined_nt'])
    axioms = _parse_nt(bundle['axioms_nt'])
    if set(full) != set(base) | set(axioms):
        raise OWLConstraintError('Combined graph differs from exact union')
    audit_structural_conformance(full, expected_nodes=len(view.graph.nodes),
                                  expected_edges=len(view.graph.edges),
                                  persisted=store_state is not None)
    return expected['manifest']


_FILES = {
    'axioms_nt': 'owl-structural-axioms.nt',
    'axioms_ttl': 'owl-structural-axioms.ttl',
    'combined_nt': 'owl-constrained-knowledge-graph.nt',
    'combined_ttl': 'owl-constrained-knowledge-graph.ttl',
    'manifest': 'g5-structural-constraints-manifest.json',
}


def _source(repository: Path, mode: str, knowledge_graph: str | None):
    view, state = _verified_view(repository, mode, knowledge_graph)
    rdf = export_view(view, store_state=state)
    base = build_owl_layer(view, rdf, store_state=state)
    return view, state, rdf, base


def write_constraint_directory(repository: Path, destination: Path, *, mode='persisted',
                               knowledge_graph=None) -> dict:
    repo = Path(repository).resolve(strict=True)
    target = _output_dir(Path(destination), repo)
    view, state, rdf, base = _source(repo, mode, knowledge_graph)
    bundle = build_constraint_layer(view, rdf, base, store_state=state)
    verify_constraint_layer(view, rdf, base, bundle, store_state=state)
    target.mkdir(mode=0o700)
    for name, filename in _FILES.items():
        data = canonical(bundle[name]) if name == 'manifest' else bundle[name]
        _new_file(target / filename, data)
    verify_constraint_layer(view, rdf, base, read_constraint_directory(target), store_state=state)
    return bundle['manifest']


def read_constraint_directory(directory: Path) -> dict:
    path = Path(directory)
    return {name: (parse(data) if name == 'manifest' else data)
            for name, filename in _FILES.items()
            for data in [_read_regular(path / filename, MAX_REPORT_BYTES if name == 'manifest'
                                      else MAX_BYTES)]}


def verify_constraint_directory(repository: Path, directory: Path, *, mode='persisted',
                                knowledge_graph=None) -> dict:
    repo = Path(repository).resolve(strict=True)
    view, state, rdf, base = _source(repo, mode, knowledge_graph)
    return verify_constraint_layer(view, rdf, base, read_constraint_directory(directory),
                                   store_state=state)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='G5.2 source-bound OWL structural profile')
    parser.add_argument('command', choices=('build', 'verify'))
    parser.add_argument('--repository', required=True)
    parser.add_argument('--mode', choices=('persisted', 'candidate'), default='persisted')
    parser.add_argument('--knowledge-graph')
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--report')
    args = parser.parse_args(argv)
    repo = Path(args.repository).resolve(strict=True)
    if args.command == 'build':
        manifest = write_constraint_directory(repo, Path(args.output_dir), mode=args.mode,
                                              knowledge_graph=args.knowledge_graph)
    else:
        manifest = verify_constraint_directory(repo, Path(args.output_dir), mode=args.mode,
                                               knowledge_graph=args.knowledge_graph)
    if args.report:
        if args.command != 'verify':
            raise OWLConstraintError('Reports require independent verification')
        output = Path(args.report).absolute()
        if (output.exists() or output.is_symlink() or output == repo or repo in output.parents
                or not output.parent.is_dir() or any(p.is_symlink() for p in output.parents)):
            raise OWLConstraintError('Unsafe report destination')
        report = {
            'schema_version': REPORT_SCHEMA,
            'source_manifest_sha256': manifest['manifest_sha256'],
            'source_g5_manifest_sha256': manifest['source_g5_manifest_sha256'],
            'constrained_property_count': manifest['constrained_property_count'],
            'structural_property_occurrences_audited': manifest['structural_property_occurrences_audited'],
            'finite_structural_conformance': True,
            'owl_reasoner_consistency_verified': False,
            'owl_entailment_verified': False,
            'scientific_truth_established': False,
            'automatic_approval_permitted': False,
            'authoritative_graph_mutation_permitted': False,
        }
        report['report_sha256'] = _sha(canonical(report))
        raw = canonical(report)
        if len(raw) > MAX_REPORT_BYTES:
            raise OWLConstraintError('Report exceeds byte budget')
        _new_file(output, raw)
    print(json.dumps(manifest, sort_keys=True, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OWLConstraintError, OWLOntologyError, RDFExportError, RDFInteroperabilityError,
            GraphStoreError, GraphDomainError, ValueError, OSError, TypeError, KeyError) as exc:
        print('G5.2 ontology constraint verification rejected:', exc, file=__import__('sys').stderr)
        raise SystemExit(2)
